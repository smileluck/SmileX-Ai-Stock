#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 推荐股票定时任务
recommend.daily_run: 周一至周五 16:45（在指数 15:30 / 板块 15:31 / 涨停 15:35 /
收盘分析 16:05 等行情快照同步完成后）自动生成当日 10 只推荐股（涨停候选/抄底两类，
含预判买点），并把推荐写成专用策略「AI每日推荐」的待执行买入信号，由交易引擎
在后续交易时段自动建仓追踪。当日已有成功/执行中记录则跳过。
任务内做交易日判定（法定节假日跳过），cron 的 mon-fri 只覆盖不到调休与节假日。

说明：与 strategy_run 相同的坑——APScheduler 星期字段 Monday=0，
数字 "1-5" 实为周二至周六，必须用 mon-fri。
"""

import logging

from core.exception.errors import CustomError
from modules.scheduler.core.registry import scheduled_task

logger = logging.getLogger(__name__)


@scheduled_task(
    cron="45 16 * * mon-fri",
    name="AI每日推荐股票生成",
    description="收盘后行情快照同步完成时，综合涨停连板/热榜情绪/板块资金/轮动评分/主力埋伏/超跌因子六维度生成当日 10 只推荐股（含预判买点），并落为「AI每日推荐」策略的买入信号供交易引擎自动建仓追踪；非交易日（法定节假日）跳过；同日已有成功/执行中记录则跳过",
    task_key="recommend.daily_run",
    is_system=True,
)
async def recommend_daily_run():
    """生成当日 AI 推荐股票（16:45，仅交易日执行）"""
    from sqlalchemy import select

    from database.db_manager import get_session
    from database.models.business.recommend import BusinessRecommendRun
    from database.utils.timezone import timezone
    from modules.recommend.services.recommend_service import RecommendService

    now = timezone.now()
    run_date = now.date()
    from modules.stock.services.trading_calendar import is_trading_day

    if not await is_trading_day(run_date):
        return {"run_date": run_date.strftime("%Y-%m-%d"), "skipped": 1, "reason": "非交易日"}
    total = {"run_date": run_date.strftime("%Y-%m-%d"), "submitted": 0, "skipped": 0, "rejected": 0}
    async for db in get_session():
        # 同日去重：已有成功/执行中记录则跳过；failed 可手动重新触发
        dup = await db.execute(
            select(BusinessRecommendRun.id).where(
                BusinessRecommendRun.run_date == run_date,
                BusinessRecommendRun.status.in_(("success", "running")),
                BusinessRecommendRun.deleted_at.is_(None),
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            total["skipped"] += 1
            return total
        try:
            run_id = await RecommendService.submit_run(db, trigger_type="schedule")
            total["submitted"] += 1
            total["run_id"] = run_id
        except CustomError:
            # 并发守卫：当日已有 running 记录（如手动触发正在进行）
            total["rejected"] += 1
    return total
