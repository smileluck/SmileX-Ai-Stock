#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
新浪行情数据源辅助层
hq.sinajs.cn 批量实时行情，作为东财（push2）不可达时的实时兜底源
- 指数/个股通用，单次请求即可批量查询（比逐个抓取快得多）
- 实时性好于 baostock 日线（盘后更新），但字段精度略低于东财
"""
import logging

import httpx

from core.datasource.gateway import call_external_async
from modules.stock.services._common import num

logger = logging.getLogger(__name__)

_QUOTE_URL = "https://hq.sinajs.cn/list={codes}"
# hq.sinajs.cn 自 2021 年起强制校验 Referer，缺失直接 403
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
}


def _parse_line(line: str):
    """解析单行行情：var hq_str_sh000001="名称,今开,昨收,最新,最高,最低,..." """
    line = line.strip()
    if not line.startswith("var hq_str_") or '="' not in line:
        return None
    code = line[len("var hq_str_"):line.index("=")]
    payload = line.split('="', 1)[1].rsplit('"', 1)[0]
    if not payload:
        return None
    f = payload.split(",")
    if len(f) < 32:
        return None

    latest = num(f[3])
    prev = num(f[2])
    high = num(f[4])
    low = num(f[5])
    quote = {
        "name": f[0].strip(),
        "open": num(f[1]),
        "prev_close": prev,
        "latest_price": latest,
        "high": high,
        "low": low,
        "volume": num(f[8]),
        "turnover": num(f[9]),
        "change_pct": round((latest - prev) / prev * 100, 4) if latest and prev else None,
        "change_amount": round(latest - prev, 4)
        if latest is not None and prev is not None
        else None,
        "amplitude": round((high - low) / prev * 100, 4)
        if high is not None and low is not None and prev
        else None,
        "trade_date": f[30] or None,
        "trade_time": f[31] or None,
    }
    return code, quote


async def fetch_spot_quotes(codes: list[str], client: httpx.AsyncClient | None = None) -> dict[str, dict]:
    """批量抓取新浪实时行情

    Args:
        codes: 新浪格式代码列表，如 ["sh000001", "sz399001", "sh600519"]
        client: 可复用的 httpx 客户端；为空则临时创建

    Returns:
        {sina_code: quote dict}，停牌/无数据代码缺席
    """
    if not codes:
        return {}

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        resp = await call_external_async(
            "sina", client.get,
            _QUOTE_URL.format(codes=",".join(codes)), headers=_HEADERS, timeout=15,
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            await client.aclose()

    text = resp.content.decode("gbk", errors="ignore")
    quotes: dict[str, dict] = {}
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed:
            quotes[parsed[0]] = parsed[1]
    return quotes
