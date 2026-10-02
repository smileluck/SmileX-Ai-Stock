#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A 股交易日历（轻量运行时判定）

判定链（逐级降级）：
1. FQGate 交易日历专用接口（core.fqgate.calendar.trading_days，无需登录行情账户）：
   交易所发布日历，含未来日期，可权威判定法定节假日与调休，结果一律可缓存；
2. FQGate 不可用/返回未覆盖判定日时，降级为上证指数日线日期集合推断
   （复用 market_fetcher.fetch_index_history 的多源降级链）；
3. 数据源全部异常时降级为「周一至周五」判断并记 warning。

结果按日内存缓存：交易引擎每分钟 tick 只查一次。

指数日线推断口径（宁可多跑、不可漏跑交易时段）：
- 当日 bar 缺失但日历数据新鲜（已覆盖到上一工作日）：判定为法定节假日休市；
- 当日 bar 缺失且日历数据陈旧（数据源滞后）：降级为工作日判断并记 warning
  （已知局限：长假第 2 个工作日起该锚点失效会误判为交易日，
  由交易引擎的行情日期新鲜度校验兜底，不会以陈旧价成交）；
- 盘前（< 9:30）当日 bar 可能尚未发布，为避免误杀 pre_market 盘前分析，
  此时当日缺失一律降级为工作日判断（休市误判的代价仅是休市日多跑一轮 LLM 分析，
  9:30 后交易引擎有确定口径兜底，不会假成交）。

缓存口径（防粘性误判）：FQGate 权威日历的判定结果全部可缓存；指数日线推断路径
只有确定性结果允许入当日缓存——当日仅「当日 bar ∈ 日历」的 True 是确定的
（数据源盘中滞后/降级时 False 可能是误判）；历史日期的判定结果全部确定。
盘前宽限、数据源故障降级、数据陈旧降级三条路径永不落缓存，每次都重新判定。
"""
import asyncio
import logging
from datetime import date, datetime, time as dt_time, timedelta

from core.fqgate import calendar as fq_calendar
from database.utils.timezone import timezone
from modules.stock.services import _fqgate
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

# FQGate 权威日历查询窗口（相对判定日：回看覆盖长假，前看覆盖未来节假日安排）
_FQ_CAL_LOOKBACK_DAYS = 30
_FQ_CAL_LOOKAHEAD_DAYS = 15

# 当日判定结果缓存：date -> bool（只会积累少量日期，超限整体重建）
_cache: dict[date, bool] = {}
_cache_lock = asyncio.Lock()


def _prev_weekday(day: date) -> date:
    """上一个工作日（周一回看至周五）"""
    prev = day - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


async def _resolve_by_fqgate_calendar(day: date) -> bool | None:
    """FQGate 交易日历专用接口权威判定（交易所发布日历，含未来日期，无需登录）。

    返回 True/False 表示权威判定；接口不可用、超时或返回日历未覆盖判定日时
    返回 None，由调用方继续走指数日线推断降级链。
    """
    key = day.isoformat()
    start = (day - timedelta(days=_FQ_CAL_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = (day + timedelta(days=_FQ_CAL_LOOKAHEAD_DAYS)).strftime("%Y%m%d")
    try:
        data = await asyncio.wait_for(
            fq_calendar.trading_days(start, end), timeout=_FETCH_TIMEOUT
        )
        days = set(_fqgate._parse_calendar_days(data))
    except Exception as exc:  # noqa: BLE001  FQGate 未运行/异常：降级指数日线推断
        logger.warning("FQGate 交易日历获取失败，降级指数日线推断: day=%s error=%s", key, exc)
        return None
    if not days or not (min(days) <= key <= max(days)):
        # 日历为空或未覆盖判定日（如网关数据只到历史某日），无法权威判定
        logger.warning("FQGate 交易日历未覆盖判定日，降级指数日线推断: day=%s", key)
        return None
    return key in days


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

    # 第一层：FQGate 权威日历（交易所发布，含未来日期，结果确定可缓存）
    fq_result = await _resolve_by_fqgate_calendar(day)
    if fq_result is not None:
        return fq_result, True

    # 第二层：指数日线日期集合推断
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
