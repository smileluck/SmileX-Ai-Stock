#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A 股交易日历（轻量运行时判定）

以上证指数日线日期集合判定某天是否交易日（法定节假日感知），
复用 market_fetcher.fetch_index_history 的多源降级链（akshare-东财 → baostock → 新浪日线）。
结果按日内存缓存：交易引擎每分钟 tick 只查一次。

降级口径（宁可多跑、不可漏跑交易时段）：
- 数据源异常/为空：降级为「周一至周五」判断并记 warning；
- 当日 bar 缺失但日历数据新鲜（已覆盖到上一工作日）：判定为法定节假日休市；
- 当日 bar 缺失且日历数据陈旧（数据源滞后）：降级为工作日判断并记 warning；
- 盘前（< 9:30）当日 bar 可能尚未发布，为避免误杀 pre_market 盘前分析，
  此时当日缺失一律降级为工作日判断（休市误判的代价仅是休市日多跑一轮 LLM 分析，
  9:30 后交易引擎有确定口径兜底，不会假成交）。

缓存口径（防粘性误判）：只有确定性结果允许入当日缓存——
当日仅「当日 bar ∈ 日历」的 True 是确定的（数据源盘中滞后/降级时 False 可能是误判）；
历史日期的判定结果全部确定。盘前宽限、数据源故障降级、数据陈旧降级三条路径
永不落缓存，每次都重新判定。
"""
import asyncio
import logging
from datetime import date, datetime, time as dt_time, timedelta

from database.utils.timezone import timezone
from modules.stock.services.market_fetcher import fetch_index_history

logger = logging.getLogger(__name__)

# 交易日历基准指数（上证指数，纯数字代码）
_CALENDAR_INDEX = "000001"

# 日历回看窗口（覆盖长假 + 数据滞后余量）
_LOOKBACK_DAYS = 20

# 单日历查询硬超时（秒）
_FETCH_TIMEOUT = 30

# 盘前宽限时点：此前当日 bar 未发布时不做休市判定
_PRE_OPEN_LENIENT_UNTIL = dt_time(9, 30)

# 当日判定结果缓存：date -> bool（只会积累少量日期，超限整体重建）
_cache: dict[date, bool] = {}
_cache_lock = asyncio.Lock()


def _prev_weekday(day: date) -> date:
    """上一个工作日（周一回看至周五）"""
    prev = day - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


async def is_trading_day(day: date) -> bool:
    """判断某天是否 A 股交易日（法定节假日感知）。

    周末直接 False 不查数据源；数据源异常时降级为工作日判断并记 warning。
    只有确定性结果入当日缓存（见模块 docstring 缓存口径）。
    """
    if day.weekday() >= 5:
        return False
    if day in _cache:
        return _cache[day]
    async with _cache_lock:
        if day in _cache:
            return _cache[day]
        result, cacheable = await _resolve_trading_day(day)
        if cacheable:
            if len(_cache) > 64:
                _cache.clear()
            _cache[day] = result
        return result


async def _resolve_trading_day(day: date) -> tuple[bool, bool]:
    """实际判定逻辑，返回 (是否交易日, 结果是否可缓存)。"""
    key = day.isoformat()
    now = timezone.now()
    is_today = day == now.date()
    try:
        start = (day - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
        items = await asyncio.wait_for(
            fetch_index_history(_CALENDAR_INDEX, start, day.strftime("%Y%m%d")),
            timeout=_FETCH_TIMEOUT,
        )
        days = {
            str(it["record_date"])[:10]
            for it in items
            if isinstance(it.get("record_date"), (str, date, datetime))
        }
        if not days:
            raise RuntimeError("交易日历数据为空")
    except Exception as exc:  # noqa: BLE001  数据源故障降级：非确定性结果不缓存
        logger.warning("交易日历获取失败，降级为周一至周五判断: day=%s error=%s", key, exc)
        return day.weekday() < 5, False

    if key in days:
        return True, True  # 当日 bar 存在是唯一确定性的当日 True

    # 盘前宽限：当日 bar 可能尚未发布，不做休市判定，非确定性结果不缓存
    if is_today and now.time() < _PRE_OPEN_LENIENT_UNTIL:
        logger.info("交易日历盘前宽限（当日 bar 未发布）: day=%s，按交易日处理", key)
        return True, False

    if max(days) >= _prev_weekday(day).isoformat():
        # 日历已覆盖到上一工作日却无当日：法定节假日休市。
        # 历史日期此判定确定；当日仍可能是数据源盘中滞后（如降级 baostock 日线
        # 盘后才有当日 bar），故当日 False 不缓存，下一 tick 重新判定可自愈
        logger.info("法定节假日休市（交易日历无当日）: day=%s", key)
        return False, not is_today
    # 数据源整体滞后（日历陈旧），无法判定，降级工作日口径，非确定性结果不缓存
    logger.warning(
        "交易日历数据陈旧（最新 %s，上一工作日 %s），降级为工作日判断: day=%s",
        max(days), _prev_weekday(day).isoformat(), key,
    )
    return True, False
