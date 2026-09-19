#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持仓跟踪日志清理定时任务
business_position_track_log 为高频快照表（交易时段每分钟每持仓一条），
每日凌晨物理删除 90 天前的历史记录防表膨胀（日志类数据不做软删除保留）

说明：本模块经 tasks/strategy_run.py 末尾导入完成装饰器注册
（main.py 只显式 import strategy_run，不再逐个追加任务模块）。
"""

import logging
from datetime import timedelta

from modules.scheduler.core.registry import scheduled_task

logger = logging.getLogger(__name__)

# track log 保留天数
_RETENTION_DAYS = 90

# 分批删除：每批行数与单次运行最大批数（防大表首次清理单条 DELETE 超时永不收敛，
# 未删完的部分次日继续）
_BATCH_SIZE = 5000
_MAX_BATCHES = 200


@scheduled_task(
    cron="23 3 * * *",
    name="持仓跟踪日志清理",
    description="每日分批物理删除 90 天前的持仓跟踪日志（business_position_track_log），防表膨胀",
    task_key="strategy.track_log_cleanup",
    timeout=600,  # 分批删除大表可能较慢，显式 10 分钟上限
    is_system=True,
)
async def strategy_track_log_cleanup():
    """分批清理过期持仓跟踪日志（SELECT id 批 + 按 id 删，MySQL/PG 通用）"""
    from sqlalchemy import delete, select

    from database.db_manager import get_session
    from database.models.business.strategy import BusinessPositionTrackLog
    from database.utils.timezone import timezone

    cutoff = timezone.now() - timedelta(days=_RETENTION_DAYS)
    total = 0
    batches = 0
    async for db in get_session():
        while batches < _MAX_BATCHES:
            ids = (
                await db.execute(
                    select(BusinessPositionTrackLog.id)
                    .where(BusinessPositionTrackLog.track_time < cutoff)
                    .limit(_BATCH_SIZE)
                )
            ).scalars().all()
            if not ids:
                break
            await db.execute(
                delete(BusinessPositionTrackLog).where(
                    BusinessPositionTrackLog.id.in_(ids)
                )
            )
            await db.commit()
            total += len(ids)
            batches += 1
            if len(ids) < _BATCH_SIZE:
                break
    if batches >= _MAX_BATCHES:
        logger.warning(
            "持仓跟踪日志清理达单次上限（%d 批 × %d 行），剩余次日继续: deleted=%d",
            _MAX_BATCHES, _BATCH_SIZE, total,
        )
    elif total:
        logger.info("持仓跟踪日志清理完成: deleted=%d cutoff=%s", total, cutoff)
    return {"deleted": total, "batches": batches}
