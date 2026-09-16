#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测行情数据抓取（baostock）

与 modules/stock/services/_baostock.py 相同的单连接串行约束：
baostock 是全局单连接协议，login/query/logout 必须在同一线程内串行完成，
故整体放入一个同步函数，经 asyncio.to_thread 执行。

不复权（adjustflag="3"）：回测需匹配真实成交价。
股票代码转换与 _baostock.to_bs_code（指数专用，0/5->sh）不同，
本模块为股票版：6->sh，0/3->sz，4/8（北交所）baostock 不支持。
"""
import asyncio
import logging

from modules.stock.services._common import num

logger = logging.getLogger(__name__)

# 日线查询字段
_BAR_FIELDS = "date,open,high,low,close,preclose,pctChg"

# 交易日历基准指数（上证指数）
_CALENDAR_INDEX = "sh.000001"


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
    """该股票代码是否可经 baostock 获取行情（北交所不支持）"""
    return to_bs_stock_code(stock_code) is not None


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


def _fetch_market_data(
    stock_codes: list[str], start_date: str, end_date: str
) -> dict:
    """（同步）单连接串行抓取：交易日历（上证指数）+ 各股票日线

    Returns:
        {
            "trading_days": [YYYY-MM-DD, ...]（升序）,
            "bars": {stock_code: [bar, ...]},
            "failed_codes": [查询失败或无数据的股票代码],
        }
    """
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")

    try:
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


async def fetch_market_data(
    stock_codes: list[str], start_date: str, end_date: str
) -> dict:
    """异步入口：抓取回测所需全部行情（交易日历 + 个股日线）

    Args:
        stock_codes: 纯数字股票代码列表（调用方应已剔除北交所等不支持代码）
        start_date / end_date: YYYY-MM-DD
    """
    return await asyncio.to_thread(
        _fetch_market_data, stock_codes, start_date, end_date
    )
