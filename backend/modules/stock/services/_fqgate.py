#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FQGate 本机行情网关数据源辅助层
默认 http://127.0.0.1:17281（同花顺数据，无需鉴权，只监听本机回环地址），
作为东财 akshare / baostock / 新浪全部不可达时的全链路兜底源：
- 日 K 线 /v1/market/history/klines（复权口径 adjust="" 不复权，匹配既有链路）
- 交易日历：FQGate 无独立日历接口，用高流动性个股（600519）日 K 推导交易日
- 实时报价 /v1/market/realtime/quote（批量）
- 健康检查 /v1/market/health

响应为统一信封 {"code": 0, "message", "data", "warnings"}，code!=0 即错误；
data.records 为「分段 → 记录 → 字段」嵌套数组，字段是同花顺协议数字编号，
值可能是裸值或 {"value": ...} / {"type": "invalid"|"no_update"} 包装。

网关未安装/未启动时连接被拒，异常向上抛由调用方降级链跳过。
"""
import logging
from typing import Any

import httpx

from core.datasource.config import DataSourceConfigProvider
from core.datasource.gateway import call_external_async
from modules.stock.services._common import num

logger = logging.getLogger(__name__)

_SOURCE = "fqgate"
# 服务端行情查询预算 30s
_SERVER_TIMEOUT_MS = "30000"

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
    client = await _client()
    try:
        data = await _post(
            client, "/v1/market/catalog/search-symbols", {"pattern": name}
        )
    except Exception:
        _symbol_cache[name] = None
        raise
    finally:
        await client.aclose()
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


def _field_value(v: Any) -> Any:
    """字段值解包：裸值直返，{"value": ...} 取值，{"type": "invalid"|"no_update"} 返回 None"""
    if isinstance(v, dict):
        if v.get("type") in ("invalid", "no_update"):
            return None
        return v.get("value")
    return v


def _flatten_records(data: dict) -> list[dict]:
    """展平 data.records 的「分段 → 记录」嵌套结构为记录列表"""
    records = (data or {}).get("records") or []
    flat: list[dict] = []
    for segment in records:
        if isinstance(segment, list):
            flat.extend(r for r in segment if isinstance(r, dict))
        elif isinstance(segment, dict):
            flat.append(segment)
    return flat


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
    """POST 并校验统一信封，返回 data"""
    resp = await call_external_async(
        _SOURCE,
        client.post,
        path,
        json=body,
        headers={"X-Request-Timeout-Ms": _SERVER_TIMEOUT_MS},
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"FQGate {path} 返回错误: {payload.get('code')} {payload.get('message')}"
        )
    return payload.get("data") or {}


async def _client() -> httpx.AsyncClient:
    cfg = await DataSourceConfigProvider.get_fqgate_gateway()
    base_url = str(cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("FQGate base_url 未配置")
    return httpx.AsyncClient(base_url=base_url, timeout=35)


async def health() -> dict:
    """健康检查，返回 {connected, network_ready, reason, account, ...}；网关未运行抛异常"""
    cfg = await DataSourceConfigProvider.get_source_config(_SOURCE)
    timeout = min(float(cfg.get("timeout_s", 32)), 10.0)
    gw = await DataSourceConfigProvider.get_fqgate_gateway()
    base_url = str(gw.get("base_url") or "").rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        resp = await client.get("/v1/market/health")
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"FQGate health 返回错误: {payload.get('message')}")
    return payload.get("data") or {}


async def fetch_daily_bars_by_security(
    sec: dict, start_date: str, end_date: str,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """按 {market, code} 抓取日 K（不复权），返回与 backtest.market_data bar 相同的
    dict 结构（按日期升序）。个股与指数通用（指数经 resolve_security 解析）。

    FQGate 日 K 无 preclose/pct_chg 字段：preclose 取前一根收盘价，
    pct_chg 按 (close - preclose) / preclose 折算。
    """
    body = {
        "market": sec["market"],
        "code": sec["code"],
        "interval": "day",
        "start_date": start_date,
        "end_date": end_date,
        "adjust": "",
    }

    owns_client = client is None
    client = client or await _client()
    try:
        data = await _post(client, "/v1/market/history/klines", body)
    finally:
        if owns_client:
            await client.aclose()

    bars: list[dict] = []
    for rec in _flatten_records(data):
        raw_date = _field_value(rec.get(_F_TIME))
        close = num(_field_value(rec.get(_F_CLOSE)))
        if raw_date is None or close is None:
            continue
        d = str(int(raw_date)) if isinstance(raw_date, float) else str(raw_date)
        # 日 K 时间为 YYYYMMDD 紧凑格式
        if len(d) == 8 and "-" not in d:
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        bars.append({
            "date": d,
            "open": num(_field_value(rec.get(_F_OPEN))),
            "high": num(_field_value(rec.get(_F_HIGH))),
            "low": num(_field_value(rec.get(_F_LOW))),
            "close": close,
            "preclose": None,
            "volume": num(_field_value(rec.get(_F_VOLUME))),
            "amount": num(_field_value(rec.get(_F_AMOUNT))),
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
    """用基准股（600519）日 K 推导交易日列表（YYYY-MM-DD 升序）"""
    bars = await fetch_daily_bars(_CALENDAR_STOCK, start_date, end_date)
    return [b["date"] for b in bars if b["date"]]


async def fetch_quotes_by_securities(securities: list[dict]) -> dict[str, dict]:
    """按 {market, code} 列表批量取实时报价，返回 {full_code: quote dict}。
    full_code 形如 USHA600519，由调用方自行映射回业务代码。"""
    if not securities:
        return {}
    body = {
        "securities": securities,
        "fields": [
            int(_F_FULL_CODE), int(_F_NAME), int(_F_LATEST), int(_F_PRECLOSE),
            int(_F_OPEN), int(_F_HIGH), int(_F_LOW), int(_F_VOLUME), int(_F_AMOUNT),
        ],
    }

    client = await _client()
    try:
        data = await _post(client, "/v1/market/realtime/quote", body)
    finally:
        await client.aclose()

    quotes: dict[str, dict] = {}
    for rec in _flatten_records(data):
        full_code = str(_field_value(rec.get(_F_FULL_CODE)) or "")
        latest = num(_field_value(rec.get(_F_LATEST)))
        prev = num(_field_value(rec.get(_F_PRECLOSE)))
        if not full_code or latest is None:
            continue
        quotes[full_code] = {
            "name": str(_field_value(rec.get(_F_NAME)) or "").strip(),
            "open": num(_field_value(rec.get(_F_OPEN))),
            "prev_close": prev,
            "latest_price": latest,
            "high": num(_field_value(rec.get(_F_HIGH))),
            "low": num(_field_value(rec.get(_F_LOW))),
            "volume": num(_field_value(rec.get(_F_VOLUME))),
            "turnover": num(_field_value(rec.get(_F_AMOUNT))),
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
