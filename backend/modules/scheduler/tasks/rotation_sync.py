#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
板块轮动分析定时任务
- 板块成分股快照同步（板块同步 15:31、涨停池 15:35 之后）
"""
import logging

from modules.scheduler.core.registry import scheduled_task

logger = logging.getLogger(__name__)


@scheduled_task(
    cron="38 15 * * mon-fri",
    name="板块成分股快照同步",
    description="收盘后抓取活跃板块（行业全量+概念涨幅前30）全部成分股写入当日快照",
    task_key="stock.rotation_stock_sync",
    is_system=True,
)
async def rotation_stock_sync():
    """板块成分股快照同步入库（轮动分析-板块内高低切换数据源）"""
    from database.db_manager import get_session
    from modules.stock.services.rotation_service import RotationService

    async for db in get_session():
        return await RotationService.sync_board_stocks(db)
