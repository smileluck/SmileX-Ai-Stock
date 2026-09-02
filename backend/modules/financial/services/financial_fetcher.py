#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
企业财报抓取层
基于 akshare 新浪财务指标接口（stock_financial_analysis_indicator）按股票抓取
最近 N 个报告期的关键财务指标，返回标准化 dict 列表。

返回字段：
    report_period / stock_name / metrics（列名→值，仅保留白名单关键指标）
"""
import asyncio
import logging
import re
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# 抓取的报告期数量（近 3 年季度报告期）
REPORT_PERIODS = 8

# 指标白名单（新浪财务指标列名 → 展示名；列名容错用包含匹配）
_METRIC_WHITELIST = {
    "摊薄每股收益(元)": "摊薄每股收益(元)",
    "加权每股收益(元)": "加权每股收益(元)",
    "每股净资产(元)": "每股净资产(元)",
    "每股资本公积金(元)": "每股资本公积金(元)",
    "净资产收益率(%)": "净资产收益率(%)",
    "主营业务收入(万元)": "主营业务收入(万元)",
    "主营业务利润(万元)": "主营业务利润(万元)",
    "营业利润(万元)": "营业利润(万元)",
    "净利润(万元)": "净利润(万元)",
    "主营业务收入增长率(%)": "主营业务收入增长率(%)",
    "净利润增长率(%)": "净利润增长率(%)",
    "主营业务成本率(%)": "主营业务成本率(%)",
    "营业利润率(%)": "营业利润率(%)",
    "销售毛利率(%)": "销售毛利率(%)",
    "资产负债率(%)": "资产负债率(%)",
    "流动比率": "流动比率",
    "速动比率": "速动比率",
    "总资产周转率(次)": "总资产周转率(次)",
    "存货周转率(次)": "存货周转率(次)",
}


def _pick_metric(col: str) -> Optional[str]:
    """列名白名单匹配（新浪接口偶有「指标-按报告期」等后缀变化，用包含匹配）"""
    for key in _METRIC_WHITELIST:
        if key.rstrip("(%)元次") and (key in col or col in key):
            return _METRIC_WHITELIST[key]
    return None


def _norm_period(val) -> Optional[str]:
    """报告期归一化为 YYYY-MM-DD"""
    if val is None:
        return None
    s = str(val).strip().replace("/", "-").replace(".", "-")
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _norm_code(stock_code: str) -> str:
    """归一化为 6 位代码（容忍 000001.SZ / sz000001 等格式）"""
    digits = re.sub(r"\D", "", str(stock_code))
    return digits.zfill(6) if digits else ""


def _to_sina_code(code: str) -> str:
    """6 位代码 → 新浪格式（sh/sz/bj 前缀）"""
    if code.startswith(("6", "9", "5")):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


async def _fetch_stock_name(code: str) -> Optional[str]:
    """新浪批量行情兜底取股票名称（新浪财务指标接口的「股票名称」列经常为空）"""
    from modules.stock.services._sina import fetch_spot_quotes

    try:
        quotes = await fetch_spot_quotes([_to_sina_code(code)])
        name = quotes.get(_to_sina_code(code), {}).get("name")
        return str(name).strip() if name else None
    except Exception:  # noqa: BLE001
        logger.warning("新浪行情取股票名称失败: %s", code, exc_info=True)
        return None


async def fetch_financial_reports(stock_code: str, start_year: Optional[str] = None) -> list[dict]:
    """新浪财务指标抓取：返回近 N 个报告期的关键指标列表（report_period 倒序）"""
    import akshare as ak

    code = _norm_code(stock_code)
    if not code:
        return []
    if start_year is None:
        start_year = str(date.today().year - 3)
    try:
        df = await asyncio.to_thread(
            lambda: ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
        )
    except Exception:  # noqa: BLE001
        logger.warning("财务指标抓取失败: %s", code, exc_info=True)
        return []
    if df is None or df.empty:
        return []

    stock_name = str(df.iloc[0].get("股票名称", "")).strip() if "股票名称" in df.columns else ""
    if not stock_name:
        stock_name = await _fetch_stock_name(code) or ""
    items: list[dict] = []
    for _, row in df.iterrows():
        period = _norm_period(row.get("日期"))
        if not period:
            continue
        metrics = {}
        for col, val in row.items():
            name = _pick_metric(str(col))
            if name is None:
                continue
            if val is None:
                continue
            # 数值保留（NaN 归 None）；其余转字符串，'nan'/'--' 等缺失占位归 None
            if isinstance(val, (int, float)):
                v = None if val != val else val
            else:
                s = str(val).strip()
                v = None if s.lower() in ('nan', 'none', '', '--', '-') else s
            if v is not None:
                metrics[name] = v
        if metrics:
            items.append({
                "stock_code": code,
                "stock_name": stock_name or None,
                "report_period": period,
                "metrics": metrics,
            })
    items.sort(key=lambda x: x["report_period"], reverse=True)
    return items[:REPORT_PERIODS]
