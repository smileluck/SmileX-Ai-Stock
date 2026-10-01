#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate A 股业务适配层（薄适配，转发到 core.fqgate）。

通用 HTTP 封装已迁移至 backend/core/fqgate/（全量端点 + 能力元数据）；
本模块只保留 A 股业务语义：
- 纯数字代码 → {market, code} 映射（6→沪 USHA，0/3→深 USZA，北交所不支持）
- 日 K 字段编号解析与 preclose/pct_chg 折算（FQGate 日 K 无此二字段）
- 交易日历：优先 /v1/market/calendar/trading-days（无需登录），
  失败时用高流动性个股（600519）日 K 推导兜底
- 实时报价结构对齐 _sina.fetch_spot_quotes

网关未安装/未启动时连接被拒，异常向上抛由调用方降级链跳过。
"""
import logging
from typing import Any

import httpx

from core.fqgate import calendar as fq_calendar
from core.fqgate import catalog as fq_catalog
from core.fqgate import client as fq_client
from core.fqgate import realtime as fq_realtime
from modules.stock.services._common import num

logger = logging.getLogger(__name__)

# K 线/报价字段编号（同花顺行情协议）
_F_TIME = "1"
_F_OPEN = "7"
_F_HIGH = "8"
_F_LOW = "9"
_F_CLOSE = "11"
_F_LATEST = "10"
_F_VOLUME = "13"
_F_AMOUNT = "19"
_F_PRECLOSE = "6"
_F_NAME = "55"
_F_FULL_CODE = "5"

# 交易日历推导基准股（高流动性，规避指数代码格式不确定性）
_CALENDAR_STOCK = "600519"

# 证券搜索解析结果缓存（name -> {market, code}），进程内有效
_symbol_cache: dict[str, dict | None] = {}


async def resolve_security(name: str) -> dict | None:
    """按名称搜索解析 FQGate {market, code}（用于指数等代码格式不确定的标的）"""
    if name in _symbol_cache:
        return _symbol_cache[name]
    try:
        data = await fq_catalog.search_symbols(name)
    except Exception:
        _symbol_cache[name] = None
        raise
    items = data.get("items") or []
    match = next(
        (it for it in items if it.get("name") == name), items[0] if items else None
    )
    resolved = (
        {"market": match["market"], "code": match["code"]}
        if match and match.get("market") and match.get("code")
        else None
    )
    _symbol_cache[name] = resolved
    return resolved


def to_fq_security(stock_code: str) -> dict | None:
    """纯数字代码 → FQGate {market, code}；北交所（4/8 开头）不支持返回 None"""
    code = stock_code.strip()
    if code.startswith("6"):
        return {"market": "USHA", "code": code}
    if code.startswith(("0", "3")):
        return {"market": "USZA", "code": code}
    return None


async def health() -> dict:
    """健康检查，返回 {connected, network_ready, reason, account, ...}；网关未运行抛异常"""
    from core.datasource.config import DataSourceConfigProvider

    cfg = await DataSourceConfigProvider.get_source_config("fqgate")
    # 健康检查走短超时，避免面板测试长时间等待
    return await fq_client.get(
        "/v1/market/health", timeout_s=min(float(cfg.get("timeout_s", 32)), 10.0)
    )


async def fetch_daily_bars_by_security(
    sec: dict, start_date: str, end_date: str,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """按 {market, code} 抓取日 K（不复权），返回与 backtest.market_data bar 相同的
    dict 结构（按日期升序）。个股与指数通用（指数经 resolve_security 解析）。

    FQGate 日 K 无 preclose/pct_chg 字段：preclose 取前一根收盘价，
    pct_chg 按 (close - preclose) / preclose 折算。
    """
    # FQGate v1.0.5 起日期范围校验要求 YYYYMMDD 紧凑格式（YYYY-MM-DD 返回 1003）
    body = {
        "market": sec["market"],
        "code": sec["code"],
        "interval": "day",
        "start_date": start_date.replace("-", ""),
        "end_date": end_date.replace("-", ""),
        "adjust": "",
    }
    # 直接走 client.post 以支持调用方传入共享连接（回测批量兜底逐票复用）
    data = await fq_client.post("/v1/market/history/klines", body, client=client)

    bars: list[dict] = []
    for rec in fq_client.flatten_records(data):
        raw_date = fq_client.field_value(rec.get(_F_TIME))
        close = num(fq_client.field_value(rec.get(_F_CLOSE)))
        if raw_date is None or close is None:
            continue
        d = str(int(raw_date)) if isinstance(raw_date, float) else str(raw_date)
        # 日 K 时间为 YYYYMMDD 紧凑格式
        if len(d) == 8 and "-" not in d:
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        bars.append({
            "date": d,
            "open": num(fq_client.field_value(rec.get(_F_OPEN))),
            "high": num(fq_client.field_value(rec.get(_F_HIGH))),
            "low": num(fq_client.field_value(rec.get(_F_LOW))),
            "close": close,
            "preclose": None,
            "volume": num(fq_client.field_value(rec.get(_F_VOLUME))),
            "amount": num(fq_client.field_value(rec.get(_F_AMOUNT))),
            "pct_chg": None,
        })
    bars.sort(key=lambda b: b["date"])
    for i, bar in enumerate(bars):
        if i == 0:
            continue
        preclose = bars[i - 1]["close"]
        bar["preclose"] = preclose
        if preclose:
            bar["pct_chg"] = round((bar["close"] - preclose) / preclose * 100, 4)
    return bars


async def fetch_daily_bars(
    stock_code: str, start_date: str, end_date: str,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """抓取个股日 K（不复权），返回与 backtest.market_data bar 相同的 dict 结构（按日期升序）"""
    sec = to_fq_security(stock_code)
    if sec is None:
        return []
    return await fetch_daily_bars_by_security(sec, start_date, end_date, client=client)


async def fetch_trading_days(start_date: str, end_date: str) -> list[str]:
    """交易日列表（YYYY-MM-DD 升序）。优先日历专用接口（无需登录），
    失败时用基准股（600519）日 K 推导兜底。"""
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    try:
        data = await fq_calendar.trading_days(start, end)
        days = _parse_calendar_days(data)
        if days:
            return days
    except Exception as exc:
        logger.warning("FQGate 日历接口失败，降级基准股日 K 推导: %s", exc)
    bars = await fetch_daily_bars(_CALENDAR_STOCK, start_date, end_date)
    return [b["date"] for b in bars if b["date"]]


def _parse_calendar_days(data: dict) -> list[str]:
    """从 trading-days 响应提取交易日，归一化为 YYYY-MM-DD 升序。

    实测 records 为日期字符串列表（如 ["20260901", ...]），
    同时兼容嵌套分段记录与 trade_days/trading_days/days 键。"""
    raw: Any = data.get("trade_days") or data.get("trading_days") or data.get("days")
    if raw is None and isinstance(data.get("records"), list):
        records = data["records"]
        # 平铺字符串/数字列表直接用，嵌套分段结构走 flatten_records
        if all(not isinstance(r, (dict, list)) for r in records):
            raw = records
        else:
            raw = fq_client.flatten_records(data)
    days: list[str] = []
    for item in raw or []:
        v = fq_client.field_value(item) if isinstance(item, dict) else item
        if v is None:
            continue
        d = str(int(v)) if isinstance(v, float) else str(v)
        if len(d) == 8 and "-" not in d:
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        days.append(d)
    return sorted(set(days))


async def fetch_quotes_by_securities(securities: list[dict]) -> dict[str, dict]:
    """按 {market, code} 列表批量取实时报价，返回 {full_code: quote dict}。
    full_code 形如 USHA600519，由调用方自行映射回业务代码。

    FQGate 要求同一次请求的证券属于同一市场，故按 market 分组逐组请求后合并。"""
    if not securities:
        return {}
    by_market: dict[str, list[dict]] = {}
    for sec in securities:
        by_market.setdefault(sec["market"], []).append(sec)

    fields = [
        int(_F_FULL_CODE), int(_F_NAME), int(_F_LATEST), int(_F_PRECLOSE),
        int(_F_OPEN), int(_F_HIGH), int(_F_LOW), int(_F_VOLUME), int(_F_AMOUNT),
    ]
    quotes: dict[str, dict] = {}
    for market_secs in by_market.values():
        data = await fq_realtime.quote(securities=market_secs, fields=fields)
        for rec in fq_client.flatten_records(data):
            full_code = str(fq_client.field_value(rec.get(_F_FULL_CODE)) or "")
            latest = num(fq_client.field_value(rec.get(_F_LATEST)))
            prev = num(fq_client.field_value(rec.get(_F_PRECLOSE)))
            if not full_code or latest is None:
                continue
            quotes[full_code] = {
                "name": str(fq_client.field_value(rec.get(_F_NAME)) or "").strip(),
                "open": num(fq_client.field_value(rec.get(_F_OPEN))),
                "prev_close": prev,
                "latest_price": latest,
                "high": num(fq_client.field_value(rec.get(_F_HIGH))),
                "low": num(fq_client.field_value(rec.get(_F_LOW))),
                "volume": num(fq_client.field_value(rec.get(_F_VOLUME))),
                "turnover": num(fq_client.field_value(rec.get(_F_AMOUNT))),
                "change_pct": round((latest - prev) / prev * 100, 4) if latest and prev else None,
                "trade_date": None,
            "trade_time": None,
        }
    return quotes


async def fetch_spot_quotes(codes: list[str]) -> dict[str, dict]:
    """批量实时报价。入参纯数字代码，返回 {原始代码: quote dict}，
    结构与 _sina.fetch_spot_quotes 的 quote 对齐（name/open/prev_close/latest_price/
    high/low/volume/turnover/change_pct），失败/停牌代码缺席。"""
    if not codes:
        return {}
    code_map: dict[str, str] = {}
    securities = []
    for c in dict.fromkeys(codes):
        sec = to_fq_security(c)
        if sec:
            securities.append(sec)
            code_map[f"{sec['market']}{sec['code']}"] = c
    if not securities:
        return {}
    raw = await fetch_quotes_by_securities(securities)
    return {
        code_map[full_code]: quote
        for full_code, quote in raw.items()
        if full_code in code_map
    }
