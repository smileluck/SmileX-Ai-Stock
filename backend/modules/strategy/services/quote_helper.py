#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
个股实时行情辅助层：新浪批量行情（经 stock 模块公开封装 fetch_sina_spot_quotes），
新浪失败时降级 FQGate 本机网关（_fqgate.fetch_spot_quotes）。
供策略建仓定价与持仓跟踪刷新使用

非交易日硬闸：当日非交易日直接返回空——FQGate 降级路径的报价无 trade_date 字段，
无法做新鲜度校验，休市日返回的上一交易日收盘价会被交易引擎当作实时价假成交，
故在源头统一拦截（交易日历本身故障降级为工作日判断时，还有下方逐票新鲜度校验
兜底新浪路径）。

新鲜度校验：报价携带的 trade_date（行情真实所属交易日）不是当日的视为陈旧快照
一律剔除——休市日/数据源滞后时新浪照常返回上一交易日收盘价快照，不剔除会被
交易引擎当作实时价假成交。trade_date 缺失不校验，由上面的非交易日硬闸兜底。
"""
import logging
from datetime import date

from database.utils.timezone import timezone
from modules.stock.services import _fqgate
from modules.stock.services.market_fetcher import fetch_sina_spot_quotes
from modules.stock.services.trading_calendar import is_trading_day

logger = logging.getLogger(__name__)


def _to_sina_code(code: str) -> str:
    """6位证券代码 → 新浪格式：sh600519 / sz000001 / bj430047 / sh510300(ETF)"""
    if code.startswith(("sh", "sz", "bj")):
        return code
    # 5=沪市 ETF/基金（510300 等），9=沪 B/科创存托；1=深市 ETF/基金/可转债（159915/123456 等）
    if code.startswith(("6", "9", "5")):
        return f"sh{code}"
    if code.startswith(("0", "2", "3", "1")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return code


def _filter_fresh(quotes: dict[str, dict], today: date) -> dict[str, dict]:
    """剔除行情日期非当日的陈旧快照；trade_date 缺失的保留（由交易日历守卫兜底）"""
    today_str = today.isoformat()
    fresh = {}
    stale = 0
    for code, q in quotes.items():
        trade_date = q.get("trade_date")
        if trade_date and str(trade_date) != today_str:
            stale += 1
            continue
        fresh[code] = q
    if stale:
        logger.warning(
            "剔除 %d 只陈旧行情快照（行情日期非当日 %s），不用于交易执行", stale, today_str
        )
    return fresh


async def fetch_latest_quotes(codes: list[str]) -> dict[str, dict]:
    """批量获取个股最新价与涨跌幅。返回 {原始6位代码: {price, change_pct, trade_date}}，
    失败/停牌/行情日期非当日（陈旧快照）的代码缺席；非交易日整体返回空。
    change_pct 为相对昨收的百分比。降级链：新浪 hq → FQGate 本机网关。"""
    if not codes:
        return {}
    today = timezone.now().date()
    if not await is_trading_day(today):
        logger.info("非交易日 %s，不提供实时行情快照", today.isoformat())
        return {}
    sina_map = {_to_sina_code(c): c for c in codes}
    try:
        quotes = await fetch_sina_spot_quotes(list(sina_map.keys()))
        result = _filter_fresh({
            sina_map[s]: {
                "price": q.get("latest_price"),
                "change_pct": q.get("change_pct"),
                "trade_date": q.get("trade_date"),
            }
            for s, q in quotes.items()
            if s in sina_map and q.get("latest_price")
        }, today)
        if result:
            return result
        logger.warning("新浪批量行情返回为空，降级 FQGate")
    except Exception as exc:  # noqa: BLE001
        logger.warning("新浪批量行情失败，降级 FQGate: %s", exc)

    try:
        fq_quotes = await _fqgate.fetch_spot_quotes(codes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FQGate 批量行情失败: %s", exc)
        return {}
    return _filter_fresh({
        code: {
            "price": q.get("latest_price"),
            "change_pct": q.get("change_pct"),
            "trade_date": q.get("trade_date"),
        }
        for code, q in fq_quotes.items()
        if q.get("latest_price")
    }, today)


async def fetch_latest_prices(codes: list[str]) -> dict[str, float]:
    """批量获取个股最新价。返回 {原始6位代码: 最新价}，失败/停牌的代码缺席。"""
    quotes = await fetch_latest_quotes(codes)
    return {code: q["price"] for code, q in quotes.items()}
