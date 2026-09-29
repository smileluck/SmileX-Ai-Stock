#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
券商研报抓取层
基于 akshare 东财个股研报接口（stock_research_report_em）按股票抓取研报列表，
返回标准化 dict 列表（按 url 去重）。

返回字段：
    stock_code / stock_name / title / url / org_name / rating / industry
    / published_date（YYYY-MM-DD）/ forecast（{年份: {eps, pe}}）
"""
import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 单次抓取保留的研报条数上限（东财接口返回全量历史，截取近期即可）
MAX_REPORTS_PER_CODE = 60

# akshare 底层 requests 无超时：源挂住时 to_thread 永不返回，会拖死整个
# 同步任务，单次调用超时后按失败跳过该个股
_AK_CALL_TIMEOUT = 30


def _norm_code(stock_code: str) -> str:
    """归一化为 6 位代码（容忍 000001.SZ / sz000001 等格式）"""
    digits = re.sub(r"\D", "", str(stock_code))
    return digits.zfill(6) if digits else ""


def _extract_forecast(row) -> Optional[dict]:
    """从东财列「YYYY-盈利预测-收益/市盈率」提取 {年份: {eps, pe}}"""
    forecast: dict = {}
    for col, val in row.items():
        m = re.match(r"^(\d{4})-盈利预测-(收益|市盈率)$", str(col))
        if not m or val is None:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v != v:  # NaN
            continue
        year, kind = m.group(1), m.group(2)
        forecast.setdefault(year, {})["eps" if kind == "收益" else "pe"] = v
    return forecast or None


async def fetch_research_reports(stock_code: str) -> list[dict]:
    """东财个股研报抓取：返回近期研报列表（published_date 倒序）"""
    import akshare as ak

    code = _norm_code(stock_code)
    if not code:
        return []
    try:
        df = await asyncio.wait_for(
            asyncio.to_thread(lambda: ak.stock_research_report_em(symbol=code)),
            timeout=_AK_CALL_TIMEOUT,
        )
    except Exception:  # noqa: BLE001
        logger.warning("个股研报抓取失败: %s", code, exc_info=True)
        return []
    if df is None or df.empty:
        return []

    items: list[dict] = []
    for _, row in df.iterrows():
        url = str(row.get("报告PDF链接") or "").strip()
        title = str(row.get("报告名称") or "").strip()
        if not url or not title:
            continue
        # 日期列可能是 date / str，归一化为 YYYY-MM-DD
        published = row.get("日期")
        published_str = None
        if published is not None:
            s = str(published).strip()
            m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
            if m:
                published_str = (
                    f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                )
        items.append({
            "stock_code": code,
            "stock_name": str(row.get("股票简称") or "").strip() or None,
            "title": title[:500],
            "url": url[:500],
            "org_name": str(row.get("机构") or "").strip() or None,
            "rating": str(row.get("东财评级") or "").strip() or None,
            "industry": str(row.get("行业") or "").strip() or None,
            "published_date": published_str,
            "forecast": _extract_forecast(row),
        })
    items.sort(key=lambda x: x.get("published_date") or "", reverse=True)
    return items[:MAX_REPORTS_PER_CODE]
