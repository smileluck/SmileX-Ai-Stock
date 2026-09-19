#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测行情数据抓取（akshare-东财主源 + baostock 降级源）

降级链（与 modules/stock/services/market_fetcher.py 同一模式：东财主源、baostock 兜底）：
- 个股日线：默认 akshare（ak.stock_zh_a_hist，东财，adjust="" 不复权以匹配既有口径）；
  失败/超时/无数据的票降级 baostock（query_history_k_data_plus，adjustflag="3"）。
- 交易日历（上证指数日线）：同样 akshare 优先、baostock 兜底。

超时熔断：
- akshare 单票 asyncio.wait_for 硬超时（_AKSHARE_STOCK_TIMEOUT），超时的票交 baostock 降级；
  票间 sleep _AKSHARE_STOCK_DELAY 防东财 push2his IP 级限流。
- baostock 是全局单连接协议，login/query/logout 必须在同一线程内串行完成，
  故整批放入一个同步函数经 asyncio.to_thread 执行，外层 asyncio.wait_for
  给整批一个总时长上限（_BAOSTOCK_BATCH_TIMEOUT）——baostock 服务端挂起时
  （login 正常但查询无响应）单票无法中途打断，整批超时后未取到的票标记失败，
  被遗弃的线程随连接泄漏但不阻塞事件循环。

返回结构保持 {"trading_days", "bars", "failed_codes"} 不变（调用方零改动），
额外附带 "data_sources"（code -> "akshare_em" | "baostock"）记录每票实际数据源。

股票代码转换：akshare 用纯数字代码；baostock 6->sh、0/3->sz，4/8（北交所）不支持。
"""
import asyncio
import logging
import time

from modules.stock.services._common import num

logger = logging.getLogger(__name__)

# 日线查询字段（volume/amount 供因子计算使用，回测引擎只读 OHLC/pct_chg，向后兼容）
_BAR_FIELDS = "date,open,high,low,close,preclose,volume,amount,pctChg"

# 交易日历基准指数（上证指数）
_CALENDAR_INDEX = "sh.000001"
_CALENDAR_INDEX_AK = "sh000001"

# akshare 单票查询硬超时（秒）
_AKSHARE_STOCK_TIMEOUT = 30
# akshare 票间间隔（秒），防东财 push2his IP 级限流
_AKSHARE_STOCK_DELAY = 0.3
# akshare 交易日历查询硬超时（秒）
_AKSHARE_CALENDAR_TIMEOUT = 30
# baostock 降级批整体超时（秒）：当前故障形态为 login 正常、查询挂起，
# 单票查询无法中途取消，只能给整批一个总上限
_BAOSTOCK_BATCH_TIMEOUT = 120


def to_bs_stock_code(stock_code: str) -> str | None:
    """纯数字股票代码转 baostock 格式：600519 -> sh.600519，000001/300750 -> sz.xxx。
    北交所（4/8 开头）baostock 不支持，返回 None。"""
    code = stock_code.strip()
    if code.startswith("6"):
        return f"sh.{code}"
    if code.startswith(("0", "3")):
        return f"sz.{code}"
    return None


def is_supported_stock(stock_code: str) -> bool:
    """该股票代码是否可经回测行情链路获取（北交所不支持）"""
    return to_bs_stock_code(stock_code) is not None


def _compact(d: str) -> str:
    """YYYY-MM-DD -> YYYYMMDD（akshare 入参格式）"""
    return d.replace("-", "")


def _row_to_bar(fields: list[str], row: list[str]) -> dict:
    """baostock 行数据转回测用 bar dict"""
    data = dict(zip(fields, row))
    return {
        "date": data.get("date") or "",
        "open": num(data.get("open")),
        "high": num(data.get("high")),
        "low": num(data.get("low")),
        "close": num(data.get("close")),
        "preclose": num(data.get("preclose")),
        "volume": num(data.get("volume")),
        "amount": num(data.get("amount")),
        "pct_chg": num(data.get("pctChg")),
    }


def _query_daily(bs, bs_code: str, start_date: str, end_date: str) -> list[dict]:
    """（同步，需在 login 后调用）查询单标的日线，按日期升序"""
    rs = bs.query_history_k_data_plus(
        bs_code,
        _BAR_FIELDS,
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="3",
    )
    if rs.error_code != "0":
        logger.warning("baostock 查询 %s 失败: %s", bs_code, rs.error_msg)
        return []
    fields = _BAR_FIELDS.split(",")
    bars = []
    while rs.next():
        bars.append(_row_to_bar(fields, rs.get_row_data()))
    return bars


def _fetch_via_baostock(
    stock_codes: list[str], start_date: str, end_date: str, need_calendar: bool
) -> dict:
    """（同步）baostock 单连接串行抓取：可选交易日历 + 各股票日线。

    Returns:
        {"trading_days": [...] | None（need_calendar=False 时）,
         "bars": {code: [bar, ...]}, "failed_codes": [...]}
    """
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")

    try:
        trading_days = None
        if need_calendar:
            calendar_bars = _query_daily(bs, _CALENDAR_INDEX, start_date, end_date)
            trading_days = [b["date"] for b in calendar_bars if b["date"]]

        bars: dict[str, list[dict]] = {}
        failed: list[str] = []
        for code in stock_codes:
            bs_code = to_bs_stock_code(code)
            if bs_code is None:
                failed.append(code)
                continue
            stock_bars = _query_daily(bs, bs_code, start_date, end_date)
            if not stock_bars:
                failed.append(code)
                continue
            bars[code] = stock_bars
    finally:
        bs.logout()

    return {"trading_days": trading_days, "bars": bars, "failed_codes": failed}


def _fetch_stock_daily_akshare(
    stock_code: str, start_date: str, end_date: str
) -> list[dict]:
    """（同步）akshare 东财个股日线（stock_zh_a_hist，adjust="" 不复权），按日期升序。

    东财日线无 preclose 字段，按「收盘 - 涨跌额」逐行折算（同为不复权口径）。
    """
    import akshare as ak

    df = ak.stock_zh_a_hist(
        symbol=stock_code,
        period="daily",
        start_date=_compact(start_date),
        end_date=_compact(end_date),
        adjust="",
    )
    if df is None or df.empty:
        return []
    bars = []
    for _, row in df.iterrows():
        d = row.get("日期")
        d = d.date().isoformat() if hasattr(d, "date") else str(d)[:10]
        close = num(row.get("收盘"))
        change = num(row.get("涨跌额"))
        preclose = (
            round(close - change, 4)
            if close is not None and change is not None
            else None
        )
        bars.append({
            "date": d,
            "open": num(row.get("开盘")),
            "high": num(row.get("最高")),
            "low": num(row.get("最低")),
            "close": close,
            "preclose": preclose,
            "volume": num(row.get("成交量")),
            "amount": num(row.get("成交额")),
            "pct_chg": num(row.get("涨跌幅")),
        })
    return bars


def _fetch_calendar_akshare(start_date: str, end_date: str) -> list[str]:
    """（同步）akshare 东财上证指数日线，返回交易日列表（YYYY-MM-DD 升序）"""
    import akshare as ak

    df = ak.stock_zh_index_daily_em(
        symbol=_CALENDAR_INDEX_AK,
        start_date=_compact(start_date),
        end_date=_compact(end_date),
    )
    if df is None or df.empty:
        return []
    days = []
    for _, row in df.iterrows():
        d = row.get("date")
        d = d.date().isoformat() if hasattr(d, "date") else str(d)[:10]
        if d:
            days.append(d)
    return days


async def fetch_market_data(
    stock_codes: list[str], start_date: str, end_date: str
) -> dict:
    """异步入口：抓取回测所需全部行情（交易日历 + 个股日线），双源降级。

    降级链：akshare-东财（主源，逐票硬超时熔断）→ baostock（降级源，整批总时长熔断）。
    每票实际数据源记录在返回值的 "data_sources" 中，降级逐票 logger.warning 标注。

    Args:
        stock_codes: 纯数字股票代码列表（调用方应已剔除北交所等不支持代码）
        start_date / end_date: YYYY-MM-DD

    Returns:
        {
            "trading_days": [YYYY-MM-DD, ...]（升序）,
            "bars": {stock_code: [bar, ...]},
            "failed_codes": [查询失败或无数据的股票代码],
            "data_sources": {stock_code: "akshare_em" | "baostock"},
        }
    """
    # ---- 交易日历：akshare 优先，baostock 兜底 ----
    trading_days: list[str] = []
    calendar_source = "akshare_em"
    try:
        trading_days = await asyncio.wait_for(
            asyncio.to_thread(_fetch_calendar_akshare, start_date, end_date),
            timeout=_AKSHARE_CALENDAR_TIMEOUT,
        )
    except Exception as e:
        logger.warning("akshare 交易日历抓取失败（降级 baostock）: %s", e)
    if not trading_days:
        calendar_source = "baostock"
        logger.warning("akshare 交易日历为空，降级 baostock")

    # ---- 个股日线：akshare 逐票（硬超时），失败票收集交 baostock ----
    bars: dict[str, list[dict]] = {}
    sources: dict[str, str] = {}
    need_fallback: list[str] = []
    for i, code in enumerate(stock_codes):
        if i > 0:
            await asyncio.sleep(_AKSHARE_STOCK_DELAY)
        try:
            stock_bars = await asyncio.wait_for(
                asyncio.to_thread(
                    _fetch_stock_daily_akshare, code, start_date, end_date
                ),
                timeout=_AKSHARE_STOCK_TIMEOUT,
            )
        except Exception as e:
            logger.warning("akshare 个股日线失败（降级 baostock, code=%s）: %s", code, e)
            stock_bars = []
        if stock_bars:
            bars[code] = stock_bars
            sources[code] = "akshare_em"
        else:
            need_fallback.append(code)

    # ---- baostock 降级批：整批一个总时长上限，挂起时未取到的票标记失败 ----
    failed: list[str] = []
    if need_fallback or calendar_source == "baostock":
        t0 = time.monotonic()
        try:
            fb = await asyncio.wait_for(
                asyncio.to_thread(
                    _fetch_via_baostock,
                    need_fallback,
                    start_date,
                    end_date,
                    calendar_source == "baostock",
                ),
                timeout=_BAOSTOCK_BATCH_TIMEOUT,
            )
            if fb["trading_days"] is not None:
                trading_days = fb["trading_days"]
            for code, stock_bars in fb["bars"].items():
                bars[code] = stock_bars
                sources[code] = "baostock"
            failed = fb["failed_codes"]
            logger.warning(
                "baostock 降级批完成：成功 %d 票，失败 %d 票（耗时 %.1fs）",
                len(fb["bars"]), len(fb["failed_codes"]), time.monotonic() - t0,
            )
        except Exception as e:
            logger.warning(
                "baostock 降级批失败/超时（%.1fs, %s），%d 票标记失败: %s",
                time.monotonic() - t0, type(e).__name__, len(need_fallback), e,
            )
            failed = list(need_fallback)

    return {
        "trading_days": trading_days,
        "bars": bars,
        "failed_codes": failed,
        "data_sources": sources,
    }
