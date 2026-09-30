#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from modules.scheduler.core.registry import scheduled_task

# 上次执行统计清理的日期（进程内标记，每日一次）
_last_cleanup_date: str | None = None


@scheduled_task(
    interval=60,
    name="数据源统计刷盘",
    description="把数据源网关内存中的用量聚合并入 sys_data_source_stat，"
                "顺带刷新数据源配置缓存、每日清理 30 天前统计",
    task_key="datasource.stats_flush",
    timeout=120,
    is_system=True,
)
async def flush_datasource_stats():
    from core.datasource.config import DataSourceConfigProvider
    from core.datasource.stats import cleanup_old, flush_to_db
    from database.utils.timezone import timezone

    flushed = await flush_to_db()
    await DataSourceConfigProvider.force_refresh()

    cleaned = 0
    global _last_cleanup_date
    now = timezone.now()
    today = now.strftime("%Y-%m-%d")
    if now.hour == 3 and _last_cleanup_date != today:
        cleaned = await cleanup_old(days=30)
        _last_cleanup_date = today

    return {"status": "ok", "flushed": flushed, "cleaned": cleaned}
