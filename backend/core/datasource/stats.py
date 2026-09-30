#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""数据源用量统计。

调用结果在内存中按 (source_key, 小时桶) 聚合，由调度任务
datasource.stats_flush（60s）批量刷盘到 sys_data_source_stat。
每源另保留最近若干条失败事件（内存环形缓冲），供面板排查。
进程重启丢失未刷盘的一分钟级增量，可接受。
"""
import logging
from collections import deque
from datetime import datetime
from threading import Lock

from database.utils.timezone import timezone

logger = logging.getLogger(__name__)

_RECENT_EVENTS_MAX = 20

# (source, hour_bucket) -> 聚合计数
_lock = Lock()
_buckets: dict[tuple[str, datetime], dict] = {}
# source -> 最近失败事件环形缓冲
_events: dict[str, deque] = {}
# source -> 最近一次成功/失败时间
_last_outcome: dict[str, dict] = {}


def _hour_bucket(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def record(source: str, outcome: str, latency_ms: int, error: str | None = None) -> None:
    """记录一次调用结果。outcome: success / fail / timeout / rejected（熔断或禁用拒绝）"""
    now = timezone.now()
    with _lock:
        key = (source, _hour_bucket(now))
        bucket = _buckets.setdefault(key, {
            "total_calls": 0, "success_calls": 0, "fail_calls": 0,
            "timeout_calls": 0, "rejected_calls": 0,
            "total_latency_ms": 0, "max_latency_ms": 0,
        })
        bucket["total_calls"] += 1
        bucket[f"{outcome}_calls"] = bucket.get(f"{outcome}_calls", 0) + 1
        bucket["total_latency_ms"] += latency_ms
        bucket["max_latency_ms"] = max(bucket["max_latency_ms"], latency_ms)

        if outcome == "success":
            _last_outcome[source] = {"last_success_at": now}
        else:
            _last_outcome[source] = {
                **_last_outcome.get(source, {}),
                "last_error_at": now,
                "last_error_msg": (error or "")[:500],
            }
            if outcome in ("fail", "timeout") and error:
                _events.setdefault(source, deque(maxlen=_RECENT_EVENTS_MAX)).appendleft({
                    "time": now.isoformat(),
                    "outcome": outcome,
                    "error": error[:500],
                    "latency_ms": latency_ms,
                })


def snapshot_state(source: str) -> dict:
    """面板展示用：最近成功/失败信息"""
    with _lock:
        return dict(_last_outcome.get(source, {}))


def recent_events(source: str | None = None) -> list[dict]:
    """最近失败事件；source 为空时返回所有源的合并列表（按时间倒序）"""
    with _lock:
        if source:
            return [dict(e, source=source) for e in _events.get(source, [])]
        merged = [
            dict(e, source=src) for src, dq in _events.items() for e in dq
        ]
    merged.sort(key=lambda e: e["time"], reverse=True)
    return merged[:_RECENT_EVENTS_MAX * 2]


async def flush_to_db() -> int:
    """把内存聚合桶刷入 sys_data_source_stat（存在则累加），返回刷入条数"""
    with _lock:
        pending = dict(_buckets)
        _buckets.clear()
    if not pending:
        return 0

    from database import get_session
    from sqlalchemy import select
    from database.models.sys.data_source import SysDataSourceStat

    written = 0
    async for db in get_session():
        for (source, hour), agg in pending.items():
            stmt = select(SysDataSourceStat).where(
                SysDataSourceStat.source_key == source,
                SysDataSourceStat.stat_hour == hour,
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = SysDataSourceStat(
                    source_key=source, stat_hour=hour,
                    total_calls=0, success_calls=0, fail_calls=0,
                    timeout_calls=0, rejected_calls=0,
                    total_latency_ms=0, max_latency_ms=0,
                )
                db.add(row)
            row.total_calls += agg["total_calls"]
            row.success_calls += agg["success_calls"]
            row.fail_calls += agg["fail_calls"]
            row.timeout_calls += agg.get("timeout_calls", 0)
            row.rejected_calls += agg.get("rejected_calls", 0)
            row.total_latency_ms += agg["total_latency_ms"]
            row.max_latency_ms = max(row.max_latency_ms, agg["max_latency_ms"])
            written += 1
        await db.commit()
        break
    return written


async def cleanup_old(days: int = 30) -> int:
    """清理 days 天前的统计数据，返回删除条数"""
    from datetime import timedelta

    from database import get_session
    from sqlalchemy import delete
    from database.models.sys.data_source import SysDataSourceStat

    cutoff = timezone.now() - timedelta(days=days)
    async for db in get_session():
        result = await db.execute(
            delete(SysDataSourceStat).where(SysDataSourceStat.stat_hour < cutoff)
        )
        await db.commit()
        return result.rowcount or 0
    return 0
