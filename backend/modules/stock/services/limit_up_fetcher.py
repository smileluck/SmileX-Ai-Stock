#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
涨停/炸板股池抓取层
- 涨停股池：akshare stock_zt_pool_em（收盘仍封板）
- 炸板股池：akshare stock_zt_pool_zbgc_em（当日触板但未封住，仅支持最近 30 个交易日）
东财涨停池无涨停原因字段，从同花顺涨停池按代码补齐（best-effort，失败置空）
"""
import asyncio
import logging

import httpx

from modules.stock.services._common import num, normalize_code, derive_market_board

logger = logging.getLogger(__name__)

_THS_LIMIT_UP_URL = "https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool"
_THS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    # 同花顺数据中心接口校验 Referer，缺失会返回错误页
    "Referer": "https://data.10jqka.com.cn/datacenterph/limitup/limtupInfo.html",
}
# 数字字段编码：代码/名称/最新价/涨跌幅/换手率/涨停原因/连板数等，照抄数据中心页面请求
_THS_FIELDS = "199112,10,9001,330324,330325,330329,133971,1968584,9003"


async def fetch_limit_up_pool(trade_date: str) -> list[dict]:
    """抓取涨停股池

    Args:
        trade_date: 交易日期 "YYYYMMDD"
    """
    import akshare as ak

    df = await asyncio.to_thread(ak.stock_zt_pool_em, date=trade_date)
    items = []
    for _, row in df.iterrows():
        code = normalize_code(row.get("代码", ""))
        if not code:
            continue

        # 振幅若接口不提供，从 high/low/prev_close 计算
        amplitude = num(row.get("振幅"))
        high = num(row.get("最高"))
        low = num(row.get("最低"))
        prev_close = num(row.get("昨收"))
        if amplitude is None and high is not None and low is not None and prev_close and prev_close != 0:
            amplitude = round((high - low) / prev_close * 100, 4)

        items.append({
            "stock_code": code,
            "stock_name": str(row.get("名称", "")).strip(),
            "market_board": derive_market_board(code),
            "latest_price": num(row.get("最新价")),
            "change_pct": num(row.get("涨跌幅")),
            "turnover_rate": num(row.get("换手率")),
            "turnover": num(row.get("成交额")),
            "amplitude": amplitude,
            "seal_amount": num(row.get("封板资金")),
            "first_limit_up_time": _fmt_time(row.get("首次封板时间")),
            "last_limit_up_time": _fmt_time(row.get("最后封板时间")),
            "break_count": num(row.get("炸板次数")),
            "consecutive_limit_up": num(row.get("连板数")),
            "industry": str(row.get("所属行业", "")).strip() or None,
        })

    if not items:
        logger.warning("涨停股池抓取返回空数据: date=%s", trade_date)

    # 东财涨停池无涨停原因字段，从同花顺涨停池按代码补齐（失败不阻塞主流程）
    try:
        reasons = await fetch_limit_up_reasons(trade_date)
    except Exception as e:
        logger.warning("同花顺涨停原因抓取失败(date=%s)，原因字段置空: %s", trade_date, e)
        reasons = {}
    for it in items:
        it["limit_up_reason"] = reasons.get(it["stock_code"])
    return items


async def fetch_broken_pool(trade_date: str) -> list[dict]:
    """抓取炸板股池（当日触及涨停但收盘未封住）

    Args:
        trade_date: 交易日期 "YYYYMMDD"

    东财炸板池无封板资金/最后封板时间/涨停原因字段，对应字段为 None；
    连板数从「涨停统计」"days/ct" 的 ct 部分 best-effort 解析。
    接口仅支持最近 30 个交易日，超期由 akshare 抛 ValueError，调用方处理。
    """
    import akshare as ak

    df = await asyncio.to_thread(ak.stock_zt_pool_zbgc_em, date=trade_date)
    items = []
    for _, row in df.iterrows():
        code = normalize_code(row.get("代码", ""))
        if not code:
            continue

        items.append({
            "stock_code": code,
            "stock_name": str(row.get("名称", "")).strip(),
            "market_board": derive_market_board(code),
            "latest_price": num(row.get("最新价")),
            "change_pct": num(row.get("涨跌幅")),
            "turnover_rate": num(row.get("换手率")),
            "turnover": num(row.get("成交额")),
            "amplitude": num(row.get("振幅")),
            "seal_amount": None,
            "first_limit_up_time": _fmt_time(row.get("首次封板时间")),
            "last_limit_up_time": None,
            "break_count": num(row.get("炸板次数")),
            "consecutive_limit_up": _parse_zt_stat(row.get("涨停统计")),
            "industry": str(row.get("所属行业", "")).strip() or None,
            "limit_up_reason": None,
        })

    if not items:
        logger.warning("炸板股池抓取返回空数据: date=%s", trade_date)
    return items


def _parse_zt_stat(val) -> int | None:
    """解析炸板池「涨停统计」"days/ct" → 连板数 ct"""
    if val is None:
        return None
    s = str(val).strip()
    if "/" not in s:
        return None
    ct = s.split("/")[-1]
    return int(ct) if ct.isdigit() else None


async def fetch_limit_up_reasons(trade_date: str) -> dict[str, str]:
    """同花顺涨停池：抓取 {股票代码: 涨停原因} 映射

    Args:
        trade_date: 交易日期 "YYYYMMDD"

    该接口 filter=HS,GEM2STAR 不覆盖北交所，缺失代码的原因保持 None；
    部分个股原因为空字符串（同花顺尚未归类），同样跳过。
    """
    reasons: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=15, headers=_THS_HEADERS) as client:
        page = 1
        while True:
            resp = await client.get(
                _THS_LIMIT_UP_URL,
                params={
                    "page": page,
                    "limit": 200,
                    "field": _THS_FIELDS,
                    "filter": "HS,GEM2STAR",
                    "order_field": "330324",
                    "order_type": 0,
                    "date": trade_date,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status_code") != 0:
                raise RuntimeError(f"同花顺涨停池返回错误: {payload}")
            data = payload.get("data") or {}
            for row in data.get("info") or []:
                code = normalize_code(row.get("code", ""))
                reason = str(row.get("reason_type") or "").strip()
                if code and reason:
                    reasons[code] = reason
            page_info = data.get("page") or {}
            if page >= int(page_info.get("count") or 1):
                break
            page += 1
            await asyncio.sleep(0.3)
    return reasons


def _fmt_time(val) -> str | None:
    """格式化封板时间：akshare 可能返回 Timestamp 或字符串"""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return None
    # 提取 HH:MM:SS 部分
    if " " in s:
        s = s.split(" ")[-1]
    return s[:20]
