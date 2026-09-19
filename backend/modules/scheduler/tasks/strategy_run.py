#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 分析策略定时任务
1. strategy_run_execute: 周一至周五 9-16 点每 10 分钟检查启用策略，
   按当前时间匹配执行时段（集合竞价/早盘/午盘/尾盘/盘后）异步提交
   LLM 分析（submit_run 落库即返回，分析在后台任务中进行）
2. strategy_trade_engine: 周一至周五 9-15 点每分钟执行模拟交易引擎 ——
   拉取策略股票实时行情，按实时价执行待执行买卖信号（模拟买卖）、
   刷新持仓最新价/浮盈并触发止损/止盈/目标价自动平仓
   （接管原 strategy.position_track 每 5 分钟持仓跟踪职责）

说明：与 stock_hot_sync 相同的坑——APScheduler 星期字段 Monday=0，
数字 "1-5" 实为周二至周六，必须用 mon-fri。
"""

import logging
from datetime import datetime, time as dt_time

from core.exception.errors import CustomError
from modules.scheduler.core.registry import scheduled_task

logger = logging.getLogger(__name__)

# 各执行时段的触发窗口（本地时区 Asia/Shanghai，周一至周五）
# 每个时段取窗口内第一次检查时触发，靠 StrategyRun 的 (strategy, run_date, run_period) 去重
_PERIOD_WINDOWS: dict[str, tuple[dt_time, dt_time]] = {
    "pre_market": (dt_time(9, 15), dt_time(9, 25)),   # 早盘集合竞价
    "morning": (dt_time(9, 30), dt_time(11, 30)),     # 早盘
    "noon": (dt_time(13, 0), dt_time(14, 30)),        # 午盘
    "tail": (dt_time(14, 30), dt_time(15, 0)),        # 尾盘
    "post_close": (dt_time(15, 5), dt_time(16, 0)),   # 盘后
}


def _match_period_window(now: datetime) -> str | None:
    """当前时间命中的执行时段窗口（仅按时刻匹配，不判交易日）"""
    current = now.time()
    for period, (start, end) in _PERIOD_WINDOWS.items():
        if start <= current <= end:
            return period
    return None


async def _match_period(now: datetime) -> str | None:
    """当前时间命中的执行时段（交易日历感知：法定节假日休市，数据源故障降级周一至周五）"""
    from modules.stock.services.trading_calendar import is_trading_day

    if not await is_trading_day(now.date()):
        return None
    return _match_period_window(now)


@scheduled_task(
    cron="*/10 9-16 * * mon-fri",
    name="AI策略时段执行",
    description="按各启用策略配置的执行时段（集合竞价/早盘/午盘/尾盘/盘后）异步提交 LLM 买卖点分析，同日同时段去重；买卖信号由模拟交易引擎按实时价执行",
    task_key="strategy.run_execute",
    is_system=True,
)
async def strategy_run_execute():
    """检查并异步提交当前时段命中的启用策略（LLM 分析在后台任务中进行）"""
    from sqlalchemy import select

    from database.db_manager import get_session
    from database.models.business.strategy import BusinessStrategyRun
    from database.utils.timezone import timezone
    from modules.strategy.services.strategy_service import StrategyService
    from modules.strategy.services.strategy_executor import StrategyExecutor
    from modules.strategy.services.rule_executor import RuleExecutor

    now = timezone.now()
    period = await _match_period(now)
    if not period:
        return {"skipped": True, "reason": "非策略执行时段"}

    run_date = now.strftime("%Y-%m-%d")
    total = {"period": period, "submitted": 0, "skipped": 0, "rejected": 0, "failed": 0}
    async for db in get_session():
        strategies = await StrategyService.get_enabled(db)
        for strategy in strategies:
            periods = strategy.execute_periods or []
            if period not in periods:
                continue
            # 同日同时段去重
            dup = await db.execute(
                select(BusinessStrategyRun.id).where(
                    BusinessStrategyRun.strategy_id == strategy.id,
                    BusinessStrategyRun.run_period == period,
                    BusinessStrategyRun.run_date == run_date,
                    BusinessStrategyRun.deleted_at.is_(None),
                ).limit(1)
            )
            if dup.scalar_one_or_none() is not None:
                total["skipped"] += 1
                continue
            try:
                # 按策略类型分流：rule-规则评估，prompt-LLM 分析（并发守卫口径一致）
                executor = RuleExecutor if strategy.strategy_type == "rule" else StrategyExecutor
                await executor.submit_run(db, strategy, run_period=period)
                total["submitted"] += 1
            except CustomError:
                # 并发守卫：该策略已有 running 记录（如手动触发正在进行）
                total["rejected"] += 1
            except Exception:  # noqa: BLE001  单策略异常不中断整批
                total["failed"] += 1
                logger.error(
                    "策略提交执行异常: strategy=%s(%s) period=%s",
                    strategy.name, strategy.id, period, exc_info=True,
                )
    return total


@scheduled_task(
    cron="* 9-15 * * mon-fri",
    name="AI策略模拟交易引擎",
    description="交易日内每分钟拉取策略股票实时行情：按实时价执行待执行买卖信号（模拟买卖）+ 刷新持仓价格浮盈 + 止损/止盈/目标价自动平仓",
    task_key="strategy.trade_engine",
    timeout=240,  # 单 tick 含一次批量行情拉取 + 全量信号/持仓处理，显式 4 分钟上限
    is_system=True,
)
async def strategy_trade_engine():
    """每分钟模拟交易引擎 tick（交易时段判断在引擎内部）"""
    from database.db_manager import get_session
    from modules.strategy.services.trade_engine import TradeEngine

    total = {}
    async for db in get_session():
        total = await TradeEngine.execute_tick(db)
    return total


# 同模块域的清理任务随本模块一并注册（main.py 只显式 import 本模块）
from modules.scheduler.tasks import strategy_track_cleanup  # noqa: F401,E402
