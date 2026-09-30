#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
新闻聚合抓取层
统一封装新闻源的抓取逻辑，返回标准化的 dict 列表。
每个 dict 包含：title / url / summary / content / source / source_name / author / raw_time
出站限流/超时统一走 core.datasource.gateway（datasource.* 配置驱动），
各源按域名/来源映射网关 source_key（东财 eastmoney / 财联社 cls / 同花顺 ths /
新浪 sina / 富途 futu / 华尔街见闻 wscn / 第一财经 yicai / 金十 jin10）
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Callable

import httpx

from core.datasource.gateway import call_external, call_external_async
from database.utils.timezone import timezone

logger = logging.getLogger(__name__)

# 新闻抓取统一请求头
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def parse_news_time(raw: str | None, now: datetime | None = None) -> datetime | None:
    """将各种相对/绝对时间字符串归一化为本地时区 datetime。

    支持格式：刚刚 / X分钟前 / X小时前 / 昨天 HH:MM / MM月DD日 HH:MM /
    YYYY-MM-DD HH:MM:SS / MM-DD HH:MM（自动补全年份）
    """
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    now = now or timezone.now()

    if raw == "刚刚":
        return now

    m = re.match(r"^(\d+)\s*分钟前$", raw)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    m = re.match(r"^(\d+)\s*小时前$", raw)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    m = re.match(r"^昨天\s*(\d{1,2}):(\d{1,2})$", raw)
    if m:
        yesterday = now.date() - timedelta(days=1)
        return timezone.now().replace(
            year=yesterday.year, month=yesterday.month, day=yesterday.day,
            hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0,
        )

    # MM月DD日 HH:MM
    m = re.match(r"^(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})$", raw)
    if m:
        month, day, hour, minute = (int(m.group(i)) for i in range(1, 5))
        year = now.year
        try:
            dt = timezone.now().replace(
                year=year, month=month, day=day, hour=hour, minute=minute,
                second=0, microsecond=0,
            )
            if dt > now + timedelta(minutes=5):
                dt = dt.replace(year=year - 1)
            return dt
        except ValueError:
            return None

    # 标准格式 YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD HH:MM
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return timezone.from_str(raw, fmt)
        except ValueError:
            continue

    # 无年份 MM-DD HH:MM（自动补全年份）
    m = re.match(r"^(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})$", raw)
    if m:
        month, day, hour, minute = (int(m.group(i)) for i in range(1, 5))
        year = now.year
        try:
            dt = timezone.now().replace(
                year=year, month=month, day=day, hour=hour, minute=minute,
                second=0, microsecond=0,
            )
            if dt > now + timedelta(minutes=5):
                dt = dt.replace(year=year - 1)
            return dt
        except ValueError:
            return None

    return None


def _strip_html(text: str | None) -> str | None:
    """去除 HTML 标签"""
    if not text:
        return text
    return re.sub(r"<[^>]+>", "", text).strip() or None


def _safe_json(resp) -> dict:
    """安全解析响应 JSON，解析失败或非对象时回退为空 dict。"""
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _item(title, url, source, source_name, summary=None, content=None, author=None, raw_time=None) -> dict:
    """构造标准化新闻 dict"""
    if not title or not url:
        return {}
    return {
        "title": (_strip_html(title) or title)[:500],
        "url": url[:1000],
        "summary": _strip_html(summary)[:1000] if summary else None,
        "content": content,
        "source": source,
        "source_name": source_name[:100],
        "author": author[:100] if author else None,
        "raw_time": raw_time[:50] if raw_time else None,
    }


def _req_trace() -> str:
    """生成东方财富 API 所需的 req_trace 参数"""
    return str(int(datetime.now().timestamp() * 1000))


# ================================================================
# 东方财富
# ================================================================
async def _fetch_eastmoney(client: httpx.AsyncClient, page_size: int) -> list[dict]:
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
    params = {
        "client": "web", "biz": "web_news_col", "column": "350",
        "page_size": page_size, "last_time": "", "req_trace": _req_trace(),
    }
    resp = await call_external_async("eastmoney", client.get, url, params=params, timeout=10)
    data = (_safe_json(resp).get("data") or {}).get("list") or []
    items = []
    for row in data:
        art = row.get("showTime") or row.get("showtime")
        items.append(_item(
            title=row.get("title"),
            url=row.get("uniqueUrl") or row.get("url"),
            source="eastmoney", source_name="东方财富",
            summary=row.get("summary") or row.get("digest"),
            raw_time=str(art) if art else None,
        ))
    return items


async def _fetch_eastmoney_global(client: httpx.AsyncClient, page_size: int) -> list[dict]:
    url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web", "biz": "web_724", "fastColumn": "102",
        "sortEnd": "", "pageSize": page_size, "req_trace": _req_trace(),
    }
    resp = await call_external_async("eastmoney", client.get, url, params=params, timeout=10)
    _d = _safe_json(resp).get("data") or {}
    data = _d.get("fastNewsList") or _d.get("list") or []
    items = []
    for row in data:
        items.append(_item(
           title=row.get("title"),
           url=row.get("url_w") or row.get("url") or row.get("uniqueUrl") or f"https://finance.eastmoney.com/a/{row.get('code')}.html",
           source="eastmoney_global", source_name="7x24全球",
            summary=row.get("digest") or row.get("summary"),
            raw_time=row.get("showtime") or row.get("showTime"),
        ))
    return items


# ================================================================
# 财联社（通过 akshare）
# ================================================================
def _make_cls_fetcher() -> Callable:
    async def _fetcher(client: httpx.AsyncClient, page_size: int) -> list[dict]:
        import akshare as ak

        df = await call_external("cls", ak.stock_info_global_cls)
        items = []
        for _, row in df.iterrows():
            title = row.get("标题") or ""
            content = str(row.get("内容") or "")
            date = str(row.get("发布日期") or "")
            tm = str(row.get("发布时间") or "")
            raw_time = f"{date} {tm}".strip() or None
            items.append(_item(
                title=str(title),
                url=f"https://www.cls.cn/telegraph/{abs(hash(title))}",
                source="cls", source_name="财联社",
                summary=_strip_html(content)[:1000],
                content=content,
                raw_time=raw_time,
            ))
        return items
    return _fetcher


# ================================================================
# 华尔街见闻
# ================================================================
def _make_wallstreetcn_fetcher(key: str, name: str, channel: str) -> Callable:
    """构造华尔街见闻频道抓取器"""
    async def _fetcher(client: httpx.AsyncClient, page_size: int) -> list[dict]:
        url = f"https://api-one-wscn.awtmt.com/apiv1/content/lives?channel={channel}&limit={page_size}"
        resp = await call_external_async("wscn", client.get, url, timeout=10)
        _d = _safe_json(resp).get("data", {}) or {}
        data = _d.get("items") or _d.get("results", [])
        items = []
        for row in data:
            # title 为空时从 content_text 的 【...】 前缀提取
            title = row.get("title") or ""
            if not title:
                ct = row.get("content_text") or row.get("description") or ""
                m = re.match(r"^【(.+?)】", ct)
                title = m.group(1) if m else (ct[:80] if ct else "")
            items.append(_item(
                title=title,
                url=row.get("uri") or f"https://wallstreetcn.com/livenews/{row.get('id')}",
                source=key, source_name=name,
                summary=row.get("content_text") or row.get("description"),
                content=row.get("content"),
                raw_time=row.get("display_time") and datetime.fromtimestamp(row["display_time"]).strftime("%Y-%m-%d %H:%M:%S"),
            ))
        return items
    return _fetcher


# ================================================================
# 第一财经
# ================================================================
async def _fetch_yicai(client: httpx.AsyncClient, page_size: int) -> list[dict]:
    url = "https://www.yicai.com/api/ajax/getlatest"
    params = {"page": 1, "size": page_size or 20}
    resp = await call_external_async("yicai", client.get, url, params=params, timeout=10)
    rows = resp.json() or []
    items = []
    for row in rows:
        link = row.get("url") or ""
        if link and not link.startswith("http"):
            link = f"https://www.yicai.com{link}"
        items.append(_item(
            title=row.get("NewsTitle"),
            url=link or f"https://www.yicai.com/news/{row.get('NewsID')}.html",
            source="yicai", source_name="第一财经",
            summary=row.get("NewsNotes") or row.get("Hl"),
            raw_time=row.get("CreateDate"),
        ))
    return items


# ================================================================
# 金十数据
# ================================================================
def _make_jin10_fetcher(key: str, name: str, important_only: bool = False) -> Callable:
    async def _fetcher(client: httpx.AsyncClient, page_size: int) -> list[dict]:
        url = "https://flash-api.jin10.com/get_flash_list"
        headers = {
            "Origin": "https://www.jin10.com",
            "Referer": "https://www.jin10.com/",
            "X-App-id": "bVBF4FyRTn5NJF5n",
            "X-Version": "1.0.0",
        }
        resp = await call_external_async(
            "jin10", client.get,
            url, params={"channel": "-8200", "vip": 1},
            headers=headers, timeout=10,
        )
        data = _safe_json(resp).get("data") or []
        if important_only:
            data = [d for d in data if d.get("important")]
        items = []
        for row in data:
            inner = row.get("data") or {}
            content = inner.get("content") or ""
            title = inner.get("title") or ""
            if not title:
                m = re.match(r"^【(.+?)】", content)
                title = m.group(1) if m else _strip_html(content)[:80]
            items.append(_item(
                title=title,
                url=f"https://flash-api.jin10.com/detail/{row.get('id')}#{key}",
                source=key, source_name=name,
                summary=_strip_html(content)[:1000],
                content=content,
                raw_time=row.get("time"),
            ))
        return items
    return _fetcher


# ================================================================
# akshare 源（同花顺 / 新浪 / 富途 / 财联社）
# ================================================================
# 新闻源 key → 网关 source_key（同花顺注册表 key 为 tonghuashun，网关侧为 ths）
_AK_DS_KEYS = {"tonghuashun": "ths", "sina": "sina", "futu": "futu"}


def _fetch_via_akshare(func_name: str, key: str, name: str) -> Callable:
    async def _fetcher(client: httpx.AsyncClient, page_size: int) -> list[dict]:
        import akshare as ak  # 延迟导入，避免无依赖时报错

        df = await call_external(_AK_DS_KEYS.get(key, key), getattr(ak, func_name))
        items = []
        for _, row in df.iterrows():
            content = row.get("内容") or row.get("content") or ""
            # 标题：优先取 标题/title 列；新浪只有 内容，标题藏在 【...】 前缀
            title = row.get("标题") or row.get("title") or ""
            if not title:
                m = re.match(r"^【(.+?)】", str(content))
                if m:
                    title = m.group(1)
            if not title:
                title = _strip_html(str(content))[:80]
            t = str(title)
            # 时间：同花顺/富途用 发布时间，新浪用 时间
            raw_time = str(
                row.get("发布时间")
                or row.get("时间")
                or row.get("datetime")
                or row.get("date")
                or ""
            )
            items.append(_item(
                title=t,
                url=str(row.get("链接") or row.get("url") or f"https://example.com/news/{key}/{abs(hash(t))}"),
                source=key, source_name=name,
                summary=_strip_html(str(content))[:1000] if content else None,
                content=str(content) if content else None,
                raw_time=raw_time or None,
            ))
        return items
    return _fetcher


# ================================================================
# 源注册表
# ================================================================
NEWS_SOURCES: list[dict] = [
    {"key": "eastmoney", "name": "东方财富", "group": "东方财富", "page_size": 30, "fetch": _fetch_eastmoney},
    {"key": "eastmoney_global", "name": "7x24全球", "group": "东方财富", "page_size": 50, "fetch": _fetch_eastmoney_global},
    {"key": "cls", "name": "财联社", "group": "财联社", "page_size": 20, "fetch": _make_cls_fetcher()},
    {"key": "tonghuashun", "name": "同花顺", "group": "同花顺", "page_size": 0, "fetch": _fetch_via_akshare("stock_info_global_ths", "tonghuashun", "同花顺")},
    {"key": "sina", "name": "新浪财经", "group": "新浪财经", "page_size": 0, "fetch": _fetch_via_akshare("stock_info_global_sina", "sina", "新浪财经")},
    {"key": "wscn_global", "name": "见闻要闻", "group": "华尔街见闻", "page_size": 50, "fetch": _make_wallstreetcn_fetcher("wscn_global", "见闻要闻", "global-channel")},
    {"key": "wscn_a_stock", "name": "见闻A股", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_a_stock", "见闻A股", "a-stock-channel")},
    {"key": "wscn_hk_stock", "name": "见闻港股", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_hk_stock", "见闻港股", "hk-stock-channel")},
    {"key": "wscn_us_stock", "name": "见闻美股", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_us_stock", "见闻美股", "us-stock-channel")},
    {"key": "wscn_forex", "name": "见闻外汇", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_forex", "见闻外汇", "forex-channel")},
    {"key": "wscn_gold", "name": "见闻黄金", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_gold", "见闻黄金", "goldc-channel")},
    {"key": "wscn_oil", "name": "见闻石油", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_oil", "见闻石油", "oil-channel")},
    {"key": "wscn_commodity", "name": "见闻大宗", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_commodity", "见闻大宗", "commodity-channel")},
    {"key": "wscn_bond", "name": "见闻债券", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_bond", "见闻债券", "bond-channel")},
    {"key": "wscn_tech", "name": "见闻科技", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_tech", "见闻科技", "tech-channel")},
    {"key": "wscn_finance", "name": "见闻金融", "group": "华尔街见闻", "page_size": 30, "fetch": _make_wallstreetcn_fetcher("wscn_finance", "见闻金融", "financing-channel")},
    {"key": "yicai", "name": "第一财经", "group": "第一财经", "page_size": 20, "fetch": _fetch_yicai},
    {"key": "jin10", "name": "金十综合", "group": "金十数据", "page_size": 20, "fetch": _make_jin10_fetcher("jin10", "金十综合")},
    {"key": "jin10_important", "name": "金十重要", "group": "金十数据", "page_size": 20, "fetch": _make_jin10_fetcher("jin10_important", "金十重要", important_only=True)},
    {"key": "futu", "name": "富途快讯", "group": "富途快讯", "page_size": 0, "fetch": _fetch_via_akshare("stock_info_global_futu", "futu", "富途快讯")},
]
