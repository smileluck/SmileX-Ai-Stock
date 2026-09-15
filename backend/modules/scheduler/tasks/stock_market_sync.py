#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A股行情定时任务
- 大盘指数同步（收盘后）
- 行业/概念板块同步
- 涨停/炸板股池同步

注意：APScheduler 的星期字段 Monday=0，数字写法 "1-5" 实为周二至周六
（周六触发、跳过周一），周一到周五必须用 mon-fri。
"""
import asyncio
import logging

from modules.scheduler.core.registry import scheduled_task

logger = logging.getLogger(__name__)


@scheduled_task(
    cron="30 15 * * mon-fri",
    name="大盘指数同步",
    description="收盘后抓取主要 A 股指数实时行情并写入当日快照",
    task_key="stock.market_sync",
    is_system=True,
)
async def market_sync():
    """大盘指数同步入库"""
    from database.db_manager import get_session
    from modules.stock.services.market_service import MarketService

    async for db in get_session():
        return await MarketService.sync_all(db)


@scheduled_task(
    cron="31 15 * * mon-fri",
    name="板块数据同步",
    description="收盘后抓取行业/概念板块列表及资金流并写入当日快照",
    task_key="stock.board_sync",
    is_system=True,
)
async def board_sync():
    """板块数据同步入库"""
    from database.db_manager import get_session
    from modules.stock.services.board_service import BoardService

    result = {}
    async for db in get_session():
        result["industry"] = await BoardService.sync_all(db, "industry")
        await asyncio.sleep(2)
        result["concept"] = await BoardService.sync_all(db, "concept")
    return result


@scheduled_task(
    cron="35 15 * * mon-fri",
    name="涨停股池同步",
    description="收盘后抓取当日涨停股池与炸板股池（涨停后破板未封住）并写入当日快照",
    task_key="stock.limit_up_sync",
    is_system=True,
)
async def limit_up_sync():
    """涨停/炸板股池同步入库"""
    from database.db_manager import get_session
    from modules.stock.services.limit_up_service import LimitUpService

    async for db in get_session():
        return await LimitUpService.sync_all(db)
