#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
大宗交易（暗盘）抓取层
统一封装东方财富大宗交易榜单的抓取逻辑，返回标准化的 dict 列表。
数据源：akshare stock_dzjy_mrtj（每日统计）/ stock_dzjy_hygtj（活跃A股统计）
出站限流/超时统一走 core.datasource.gateway（datasource.* 配置驱动）
"""
import logging
from datetime import date

import httpx

from core.datasource.gateway import call_external
from modules.stock.services._common import num, normalize_code

logger = logging.getLogger(__name__)


def _to_date(val) -> date | None:
    """安全转 date，接受 'YYYY-MM-DD' / 'YYYY/MM/DD' / datetime / date"""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip().replace("/", "-")
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None

# 活跃A股统计支持的统计窗口
ACTIVE_WINDOWS: list[str] = ["近一月", "近三月", "近六月", "近一年"]


def _int(val) -> int | None:
    """安全转 int，失败返回 None"""
    n = num(val)
    return int(n) if n is not None else None


# ================================================================
# 每日统计（stock_dzjy_mrtj）
# ================================================================
async def fetch_daily(
    client: httpx.AsyncClient,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """东方财富大宗交易每日统计

    akshare 返回日期区间内按个股聚合的每日大宗交易统计；
    这里抓取指定区间，调用方通常传同一天日期取当日快照。

    返回标准化 dict 列表，字段：
        record_date / stock_code / stock_name / change_pct / close_price /
        trade_price / premium_rate / trade_count / trade_volume /
        trade_amount(万元) / amount_ratio(%)
    """
    import akshare as ak

    try:
        df = await call_external(
            "eastmoney", ak.stock_dzjy_mrtj, start_date=start_date, end_date=end_date
        )
    except (TypeError, KeyError) as exc:
        # 东财对无数据日期/限流时返回 result: null，akshare 未做空值判断直接取
        # data_json["result"]["data"] 触发 TypeError；这里视为无数据。
        logger.warning("东财大宗交易每日统计无数据或被限流(%s -> %s): %s", start_date, end_date, exc)
        return []
    if df is None or df.empty:
        return []

    items: list[dict] = []
    for _, row in df.iterrows():
        code = normalize_code(row.get("证券代码"))
        name = str(row.get("证券简称", "")).strip()
        if not code or not name:
            continue
        items.append({
            "record_date": str(row.get("交易日期", "")).strip() or None,
            "stock_code": code,
            "stock_name": name[:50],
            "change_pct": num(row.get("涨跌幅")),
            "close_price": num(row.get("收盘价")),
            "trade_price": num(row.get("成交价")),
            "premium_rate": num(row.get("折溢率")),
            "trade_count": _int(row.get("成交笔数")),
            "trade_volume": num(row.get("成交总量")),
            "trade_amount": num(row.get("成交总额")),
            "amount_ratio": num(row.get("成交总额/流通市值")),
        })
    return [it for it in items if it["record_date"]]


# ================================================================
# 活跃A股统计（stock_dzjy_hygtj）
# ================================================================
async def fetch_active(
    client: httpx.AsyncClient,
    stat_window: str,
) -> list[dict]:
    """东方财富大宗交易活跃A股统计

    akshare 按 symbol（统计窗口）返回个股大宗交易上榜频次排行。

    返回标准化 dict 列表，字段：
        stat_window / stock_code / stock_name / latest_price / change_pct /
        last_list_date / list_count_total / list_count_premium /
        list_count_discount / total_amount(万元) / premium_rate /
        amount_ratio(%) / avg_change_1d / avg_change_5d /
        avg_change_10d / avg_change_20d
    """
    import akshare as ak

    try:
        df = await call_external("eastmoney", ak.stock_dzjy_hygtj, symbol=stat_window)
    except (TypeError, KeyError) as exc:
        # 同 fetch_daily：东财返回空 / 限流时 akshare 内部取 result.data 报错
        logger.warning("东财大宗交易活跃A股无数据或被限流(%s): %s", stat_window, exc)
        return []
    if df is None or df.empty:
        return []

    items: list[dict] = []
    for _, row in df.iterrows():
        code = normalize_code(row.get("证券代码"))
        name = str(row.get("证券简称", "")).strip()
        if not code or not name:
            continue

        last_list = str(row.get("最近上榜日", "")).strip()
        items.append({
            "stat_window": stat_window,
            "stock_code": code,
            "stock_name": name[:50],
            "latest_price": num(row.get("最新价")),
            "change_pct": num(row.get("涨跌幅")),
            "last_list_date": _to_date(last_list),
            "list_count_total": _int(row.get("上榜次数-总计")),
            "list_count_premium": _int(row.get("上榜次数-溢价")),
            "list_count_discount": _int(row.get("上榜次数-折价")),
            "total_amount": num(row.get("总成交额")),
            "premium_rate": num(row.get("折溢率")),
            "amount_ratio": num(row.get("成交总额/流通市值")),
            "avg_change_1d": num(row.get("上榜日后平均涨跌幅-1日")),
            "avg_change_5d": num(row.get("上榜日后平均涨跌幅-5日")),
            "avg_change_10d": num(row.get("上榜日后平均涨跌幅-10日")),
            "avg_change_20d": num(row.get("上榜日后平均涨跌幅-20日")),
        })
    return items
