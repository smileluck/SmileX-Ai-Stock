#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
宏观经济指标抓取层
基于 akshare 抓取中美宏观指数（CPI/PPI/M1/M2 等），返回标准化 dict 列表。

数据源（实测列名，金十数据源为 {商品, 日期(发布日), 今值, 预测值, 前值} 格式）：
- 中国 CPI 同比：macro_china_cpi_yearly（今值=同比%）
- 中国 PPI 同比：macro_china_ppi_yearly（今值=同比%）
- 中国货币供应：macro_china_money_supply（国家统计局，月份 + M0/M1/M2 数量与同比/环比）
- 美国 CPI 月率：macro_usa_cpi_monthly（今值=环比%）
- 美国核心 CPI 月率：macro_usa_core_cpi_monthly（今值=环比%）

period 统一取发布日的 YYYY-MM（金十源的日期为发布日，近似对应数据期）。
"""
import asyncio
import logging
import math
from datetime import date
from typing import Optional

from modules.stock.services._common import num

logger = logging.getLogger(__name__)

# akshare 底层 requests 多数接口无超时：数据源挂住时 to_thread 永不返回，
# 会把整个任务拖到 timeout 上限（2026-09-22 起宏观/研报/财报任务连续
# 300s 超时即此因），单次调用超时后按失败跳过
_AK_CALL_TIMEOUT = 30


def _pick(row, *names) -> Optional[float]:
    """按候选列名取第一个非空数值（列名容错）"""
    for name in names:
        v = num(row.get(name))
        if v is not None and not math.isnan(v):
            return v
    return None


def _norm_period(val) -> Optional[str]:
    """日期归一化为 YYYY-MM（容忍 date / '2026-07' / '2026年7月' / '2026-07-15' 等）"""
    if val is None:
        return None
    if isinstance(val, date):
        return f"{val.year:04d}-{val.month:02d}"
    s = str(val).strip().replace("年", "-").replace("月份", "").replace("月", "").replace(".", "-").replace("/", "-")
    parts = [p for p in s.split("-") if p]
    if not parts:
        return None
    try:
        year = int(parts[0][:4])
        month = int(parts[1]) if len(parts) > 1 else 1
        if 1990 <= year <= 2100 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    except (ValueError, IndexError):
        return None
    return None


async def _fetch_df(func, **kwargs):
    """akshare 同步接口转异步（线程池），异常/超时记 WARNING 返回 None"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(lambda: func(**kwargs)), timeout=_AK_CALL_TIMEOUT
        )
    except Exception:  # noqa: BLE001
        logger.warning("宏观指标抓取失败: %s", getattr(func, "__name__", func), exc_info=True)
        return None


def _jin10_items(
    df, country: str, indicator_code: str, indicator_name: str, source: str,
    mode: str = "yoy",
) -> list[dict]:
    """金十数据源行 → 标准化记录（mode: yoy-今值记同比，mom-今值记环比；今值 nan 的未发布期跳过）"""
    items = []
    for _, row in df.iterrows():
        period = _norm_period(row.get("日期"))
        value = _pick(row, "今值")
        if not period or value is None:
            continue
        items.append({
            "country": country, "indicator_code": indicator_code, "indicator_name": indicator_name,
            "period": period, "value": value,
            "yoy": value if mode == "yoy" else None,
            "mom": value if mode == "mom" else None,
            "unit": "%", "source": source,
        })
    return items


async def fetch_china_cpi() -> list[dict]:
    """中国 CPI 同比（金十 今值）"""
    import akshare as ak

    df = await _fetch_df(ak.macro_china_cpi_yearly)
    if df is None or df.empty:
        return []
    return _jin10_items(
        df, "CN", "cpi", "CPI（居民消费价格指数同比）", "macro_china_cpi_yearly", mode="yoy",
    )


async def fetch_china_ppi() -> list[dict]:
    """中国 PPI 同比（金十 今值）"""
    import akshare as ak

    df = await _fetch_df(ak.macro_china_ppi_yearly)
    if df is None or df.empty:
        return []
    return _jin10_items(
        df, "CN", "ppi", "PPI（工业生产者出厂价格指数同比）", "macro_china_ppi_yearly", mode="yoy",
    )


async def fetch_china_money_supply() -> list[dict]:
    """中国货币供应 M0/M1/M2（国家统计局：数量-亿元 + 同比/环比增速%）"""
    import akshare as ak

    df = await _fetch_df(ak.macro_china_money_supply)
    if df is None or df.empty:
        return []
    # 实测列名（含中划线变体容错）
    specs = [
        ("m2", "M2（广义货币供应量）",
         ("货币和准货币(M2)-数量(亿元)", "M2数量"),
         ("货币和准货币(M2)-同比增长", "M2同比增长"),
         ("货币和准货币(M2)-环比增长", "M2环比增长")),
        ("m1", "M1（狭义货币供应量）",
         ("货币(M1)-数量(亿元)", "M1数量"),
         ("货币(M1)-同比增长", "M1同比增长"),
         ("货币(M1)-环比增长", "M1环比增长")),
        ("m0", "M0（流通中现金）",
         ("流通中的现金(M0)-数量(亿元)", "M0数量"),
         ("流通中的现金(M0)-同比增长", "M0同比增长"),
         ("流通中的现金(M0)-环比增长", "M0环比增长")),
    ]
    items = []
    for _, row in df.iterrows():
        period = _norm_period(row.get("月份"))
        if not period:
            continue
        for code, name, val_cols, yoy_cols, mom_cols in specs:
            value = _pick(row, *val_cols)
            yoy = _pick(row, *yoy_cols)
            mom = _pick(row, *mom_cols)
            if value is None and yoy is None and mom is None:
                continue
            items.append({
                "country": "CN", "indicator_code": code, "indicator_name": name,
                "period": period, "value": value, "yoy": yoy, "mom": mom,
                "unit": "亿元" if value is not None else "%",
                "source": "macro_china_money_supply",
            })
    return items


async def fetch_usa_cpi() -> list[dict]:
    """美国 CPI 月率（金十 今值=环比%）"""
    import akshare as ak

    df = await _fetch_df(ak.macro_usa_cpi_monthly)
    if df is None or df.empty:
        return []
    return _jin10_items(
        df, "US", "cpi", "美国 CPI 月率", "macro_usa_cpi_monthly", mode="mom",
    )


async def fetch_usa_core_cpi() -> list[dict]:
    """美国核心 CPI 月率（金十 今值=环比%）"""
    import akshare as ak

    df = await _fetch_df(ak.macro_usa_core_cpi_monthly)
    if df is None or df.empty:
        return []
    return _jin10_items(
        df, "US", "core_cpi", "美国核心 CPI 月率", "macro_usa_core_cpi_monthly", mode="mom",
    )


# 全量抓取入口（同步任务/手动触发共用）
async def fetch_all() -> dict[str, list[dict]]:
    """抓取全部宏观指标，返回 {来源key: 标准化记录列表}"""
    return {
        "china_cpi": await fetch_china_cpi(),
        "china_ppi": await fetch_china_ppi(),
        "china_money": await fetch_china_money_supply(),
        "usa_cpi": await fetch_usa_cpi(),
        "usa_core_cpi": await fetch_usa_core_cpi(),
    }
