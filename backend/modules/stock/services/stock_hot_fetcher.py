#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
股票热榜抓取层
统一封装多源热榜的抓取逻辑，返回标准化的 dict 列表。
每个 dict 包含：stock_code / stock_name / rank / latest_price / change_pct / hot_value
出站限流/超时统一走 core.datasource.gateway（datasource.* 配置驱动）
"""
import logging
import re

import httpx

from core.datasource.gateway import call_external, call_external_async

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _num(val) -> float | None:
    """安全转 float，失败返回 None"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("%", "").replace(",", "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _normalize_code(raw) -> str:
    """规范化股票代码：剥离交易所前缀，返回纯数字代码。

    各源格式不一致：雪球带 'SH600519' 前缀，东财/同花顺为纯数字；
    统一成纯数字，避免前端跳转拼接出 'SZSH600519' 这类无效链接。
    """
    s = str(raw).strip().upper()
    s = re.sub(r"^(SH|SZ|BJ)|\.(SH|SZ|BJ)$", "", s)
    return s[:20]


def _to_sina_code(pure_code: str) -> str:
    """纯数字代码 → 新浪行情代码（按首位推断交易所，与前端 openStockPage 口径一致）

    6 开头 → sh（沪市主板/科创板），4/8 开头 → bj（北交所），其余 → sz（深市主板/创业板）。
    """
    c = str(pure_code)
    if c.startswith("6"):
        return f"sh{c}"
    if c.startswith(("4", "8")):
        return f"bj{c}"
    return f"sz{c}"


async def _fill_quotes(client: httpx.AsyncClient, items: list[dict]) -> list[dict]:
    """新浪批量行情补全：只填充 items 中为空的字段，不覆盖源站原值。

    各榜单源返回的字段不齐：雪球两榜无涨跌幅、同花顺无最新价、
    东财报价补充失败时只剩排名。这里统一用新浪 hq 批量行情补齐
    stock_name / latest_price / change_pct 的空缺；失败仅告警不阻断。
    """
    from modules.stock.services._sina import fetch_spot_quotes

    need_codes = [
        it["stock_code"] for it in items
        if it.get("latest_price") is None or it.get("change_pct") is None
        or not it.get("stock_name") or it["stock_name"] == it["stock_code"]
    ]
    if not need_codes:
        return items

    quotes: dict[str, dict] = {}
    try:
        quotes = await fetch_spot_quotes(
            [_to_sina_code(c) for c in need_codes], client=client
        )
    except Exception as e:
        logger.warning("热榜行情补全失败，保留源站原始字段: %s", e)
        return items

    for it in items:
        q = quotes.get(_to_sina_code(it["stock_code"])) or {}
        if not q:
            continue
        if not it.get("stock_name") or it["stock_name"] == it["stock_code"]:
            it["stock_name"] = str(q.get("name") or it["stock_name"])[:50]
        if it.get("latest_price") is None:
            it["latest_price"] = q.get("latest_price")
        if it.get("change_pct") is None:
            it["change_pct"] = q.get("change_pct")
    return items


def _item(stock_code, stock_name, rank, latest_price=None, change_pct=None, hot_value=None) -> dict:
    """构造标准化热榜 dict"""
    if not stock_code or not stock_name:
        return {}
    return {
        "stock_code": _normalize_code(stock_code),
        "stock_name": str(stock_name).strip()[:50],
        "rank": int(rank),
        "latest_price": _num(latest_price),
        "change_pct": _num(change_pct),
        "hot_value": _num(hot_value),
    }


# ================================================================
# 东方财富
# ================================================================
async def _fetch_em_rank(client: httpx.AsyncClient) -> list[dict]:
    """东方财富个股人气榜

    emappdata 的 getAllCurrentList 只返回 代码(sc)/排名(rk)/排名变化(rc,hisRc)，
    无行情也无热度值：
    - 名称/最新价/涨跌幅经 _fill_quotes 由新浪批量行情补全；
    - 热度用 101-排名 的合成指数填充（非源站原始数据），保证热度列可展示。
    """
    resp = await call_external_async(
        "eastmoney", client.post,
        "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
        json={
            "appId": "appId01",
            "globalId": "786e4c21-70dc-435a-93bb-38",
            "marketType": "",
            "pageNo": 1,
            "pageSize": 100,
        },
        timeout=15,
    )
    resp.raise_for_status()
    rows = (resp.json() or {}).get("data") or []
    if not rows:
        raise RuntimeError("东财人气榜返回空数据")

    items = []
    for row in rows:
        sc = str(row.get("sc", "")).strip()
        rank = row.get("rk")
        items.append(_item(
            stock_code=sc,
            stock_name=_normalize_code(sc),  # 占位为纯数字代码，_fill_quotes 识别后替换为新浪名称
            rank=rank,
            hot_value=(101 - int(rank)) if rank is not None else None,
        ))
    items = [it for it in items if it]
    return await _fill_quotes(client, items)


# ================================================================
# 雪球
# ================================================================
async def _fetch_xq(client: httpx.AsyncClient, func_name: str) -> list[dict]:
    """雪球热度排行榜（akshare stock_hot_follow_xq / stock_hot_tweet_xq）

    雪球代码带 SH/SZ 前缀，由 _normalize_code 统一剥离为纯数字；
    akshare 返回的是全量股票（5000+），这里截断为热榜 Top 100。
    akshare 只返回 代码/简称/关注/最新价 四列，无涨跌幅，
    由 _fill_quotes 经新浪行情补齐。
    """
    import akshare as ak

    df = await call_external("xueqiu", getattr(ak, func_name), "最热门")
    items = []
    top_n = 100
    for idx, (_, row) in enumerate(df.iterrows(), 1):
        if idx > top_n:
            break
        items.append(_item(
            stock_code=row.get("股票代码"),
            stock_name=row.get("股票简称"),
            rank=idx,
            latest_price=row.get("最新价"),
            hot_value=row.get("关注"),
        ))
    return await _fill_quotes(client, [it for it in items if it])


def _make_xq_fetcher(func_name: str):
    async def _fetcher(client: httpx.AsyncClient) -> list[dict]:
        return await _fetch_xq(client, func_name)
    return _fetcher


# ================================================================
# 同花顺（自研 httpx 抓取）
# ================================================================
async def _fetch_ths_hot(client: httpx.AsyncClient) -> list[dict]:
    """同花顺热门股人气榜

    通过同花顺"富贵" hot_list 接口获取沪深 A 股热度排行（返回 JSON），
    接口无最新价字段，由 _fill_quotes 经新浪行情补齐；
    失败时抛异常，由 StockHotService.sync_all 捕获并记录 sync_log。
    """
    headers = {
        **_HEADERS,
        "Referer": "https://stockpage.10jqka.com.cn/",
    }
    url = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
    params = {
        "stock_type": "a",
        "type": "day",
        "list_type": "normal",
        "page_size": 100,
        "page": 1,
    }
    resp = await call_external_async("ths", client.get, url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()

    payload = resp.json()
    if payload.get("status_code") != 0:
        raise RuntimeError(
            f"同花顺热榜接口返回错误: {payload.get('status_msg', 'unknown')}"
        )

    stock_list = (payload.get("data") or {}).get("stock_list") or []
    items: list[dict] = []
    for entry in stock_list:
        items.append(_item(
            stock_code=entry.get("code"),
            stock_name=entry.get("name"),
            rank=entry.get("order"),
            change_pct=entry.get("rise_and_fall"),
            hot_value=entry.get("rate"),
        ))

    if not items:
        raise RuntimeError("同花顺热榜返回空数据")
    return await _fill_quotes(client, items)


# ================================================================
# 源注册表
# ================================================================
STOCK_HOT_SOURCES: list[dict] = [
    {"key": "em_rank", "name": "东财人气榜", "group": "东方财富", "fetch": _fetch_em_rank},
    {"key": "xq_follow", "name": "雪球关注榜", "group": "雪球", "fetch": _make_xq_fetcher("stock_hot_follow_xq")},
    {"key": "xq_tweet", "name": "雪球讨论榜", "group": "雪球", "fetch": _make_xq_fetcher("stock_hot_tweet_xq")},
    {"key": "ths_hot", "name": "同花顺热榜", "group": "同花顺", "fetch": _fetch_ths_hot},
]
