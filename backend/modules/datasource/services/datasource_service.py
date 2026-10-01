#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据源管理服务：注册表 + 运行时状态 + 用量统计 + 限流/熔断配置读写
"""
import json
import logging
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.datasource import stats as ds_stats
from core.datasource import throttle as ds_throttle
from core.datasource.config import (
    FQGATE_CONFIG_KEY,
    DEFAULT_SOURCE_CONFIGS,
    DataSourceConfigProvider,
)
from core.datasource.registry import SOURCE_REGISTRY
from core.exception.errors import RequestError
from core.i18n import t
from database.models.sys.config import ConfigGroup, ConfigType, SysConfig
from database.models.sys.data_source import SysDataSourceStat
from database.utils.timezone import timezone

logger = logging.getLogger(__name__)

_CONFIG_KEY_PREFIX = "datasource."

# 配置项校验规则：字段 -> (类型, 最小, 最大)
_CONFIG_RULES: dict[str, tuple[type, Any, Any]] = {
    "enabled": (bool, None, None),
    "max_concurrency": (int, 1, 100),
    "min_interval_ms": (int, 0, 60000),
    "timeout_s": ((int, float), 1, 300),
    "failure_threshold": (int, 1, 100),
    "cooldown_s": (int, 1, 86400),
    "circuit_mode": (str, ("auto", "force_open", "force_closed"), None),
}


class DataSourceService:
    """数据源管理服务类"""

    # ------------------------------------------------------------------
    # 列表：注册表 + 运行时状态 + 今日用量 + 当前配置
    # ------------------------------------------------------------------
    @staticmethod
    async def list_sources(db: AsyncSession) -> dict:
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(
                SysDataSourceStat.source_key,
                func.sum(SysDataSourceStat.total_calls).label("total"),
                func.sum(SysDataSourceStat.success_calls).label("success"),
                func.sum(SysDataSourceStat.fail_calls).label("fail"),
                func.sum(SysDataSourceStat.timeout_calls).label("timeout"),
                func.sum(SysDataSourceStat.rejected_calls).label("rejected"),
                func.sum(SysDataSourceStat.total_latency_ms).label("total_latency"),
                func.max(SysDataSourceStat.max_latency_ms).label("max_latency"),
            )
            .where(SysDataSourceStat.deleted_at.is_(None))
            .where(SysDataSourceStat.stat_hour >= today_start)
            .group_by(SysDataSourceStat.source_key)
        )
        rows = (await db.execute(stmt)).all()
        today_map = {r.source_key: r for r in rows}

        sources = []
        for key, meta in SOURCE_REGISTRY.items():
            cfg = await DataSourceConfigProvider.get_source_config(key)
            runtime = ds_throttle.runtime_state(key)
            outcome = ds_stats.snapshot_state(key)
            today = today_map.get(key)
            today_info = None
            if today and today.total:
                today_info = {
                    "total": today.total,
                    "success": today.success,
                    "fail": today.fail,
                    "timeout": today.timeout,
                    "rejected": today.rejected,
                    "avg_latency_ms": int(today.total_latency / today.total),
                    "max_latency_ms": today.max_latency,
                }
            sources.append({
                "key": key,
                "name": meta["name"],
                "category": meta["category"],
                "capabilities": meta.get("capabilities") or [],
                "call_sites": meta["call_sites"],
                "config": cfg,
                "circuit_state": ds_throttle.circuit_state(key, cfg),
                "consecutive_failures": runtime["consecutive_failures"],
                "circuit_recover_in_s": runtime["circuit_recover_in_s"],
                "last_success_at": outcome.get("last_success_at"),
                "last_error_at": outcome.get("last_error_at"),
                "last_error_msg": outcome.get("last_error_msg"),
                "today": today_info,
            })

        fqgate_gateway = await DataSourceConfigProvider.get_fqgate_gateway()
        return {"sources": sources, "fqgate_gateway": fqgate_gateway}

    # ------------------------------------------------------------------
    # 配置更新（写 sys_config + 失效缓存 + 重置运行时熔断状态）
    # ------------------------------------------------------------------
    @staticmethod
    async def update_source_config(db: AsyncSession, source: str, patch: dict) -> dict:
        if source not in SOURCE_REGISTRY and source not in DEFAULT_SOURCE_CONFIGS:
            raise RequestError(msg=t("dataSource.unknown_source", source=source))
        cleaned = _validate_config_patch(patch)

        key = f"{_CONFIG_KEY_PREFIX}{source}"
        row = await _get_config_row(db, key)
        stored: dict = {}
        if row is not None:
            try:
                stored = json.loads(row.value)
            except (ValueError, TypeError):
                stored = {}
        stored.update(cleaned)
        value = json.dumps(stored, ensure_ascii=False)
        defaults = json.dumps(
            DEFAULT_SOURCE_CONFIGS.get(source, {}), ensure_ascii=False
        )
        if row is None:
            row = SysConfig(
                key=key,
                value=value,
                default_value=defaults,
                description=f"数据源 [{source}] 出站限流/熔断配置",
                type=ConfigType.JSON,
                group=ConfigGroup.NETWORK,
                is_system=False,
            )
            db.add(row)
        else:
            row.value = value
        await db.flush()

        DataSourceConfigProvider.invalidate()
        # 配置变更后清空熔断/失败计数，让新配置立即生效
        ds_throttle.reset_runtime(source)
        logger.info("数据源配置已更新: %s -> %s", key, cleaned)
        merged = dict(DEFAULT_SOURCE_CONFIGS.get(source, {}))
        merged.update(stored)
        return merged

    @staticmethod
    async def update_fqgate_gateway(db: AsyncSession, base_url: str) -> dict:
        base_url = base_url.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise RequestError(msg=t("dataSource.invalid_base_url"))
        row = await _get_config_row(db, FQGATE_CONFIG_KEY)
        value = json.dumps({"base_url": base_url}, ensure_ascii=False)
        if row is None:
            row = SysConfig(
                key=FQGATE_CONFIG_KEY,
                value=value,
                default_value=json.dumps({"base_url": "http://127.0.0.1:17281"}),
                description="FQGate 本机行情网关连接配置",
                type=ConfigType.JSON,
                group=ConfigGroup.NETWORK,
                is_system=False,
            )
            db.add(row)
        else:
            row.value = value
        await db.flush()
        DataSourceConfigProvider.invalidate()
        logger.info("FQGate 网关配置已更新: %s", base_url)
        return {"base_url": base_url}

    # ------------------------------------------------------------------
    # 用量统计与失败事件
    # ------------------------------------------------------------------
    @staticmethod
    async def get_stats(db: AsyncSession, days: int = 7) -> list[dict]:
        days = min(max(days, 1), 30)
        from datetime import timedelta

        since = timezone.now() - timedelta(days=days)
        stmt = (
            select(SysDataSourceStat)
            .where(SysDataSourceStat.deleted_at.is_(None))
            .where(SysDataSourceStat.stat_hour >= since)
            .order_by(SysDataSourceStat.stat_hour.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "source_key": r.source_key,
                "stat_hour": r.stat_hour.isoformat() if r.stat_hour else None,
                "total_calls": r.total_calls,
                "success_calls": r.success_calls,
                "fail_calls": r.fail_calls,
                "timeout_calls": r.timeout_calls,
                "rejected_calls": r.rejected_calls,
                "avg_latency_ms": int(r.total_latency_ms / r.total_calls)
                if r.total_calls else 0,
                "max_latency_ms": r.max_latency_ms,
            }
            for r in rows
        ]

    @staticmethod
    async def get_events(source: str | None = None) -> list[dict]:
        return ds_stats.recent_events(source)

    # ------------------------------------------------------------------
    # FQGate 连通性测试
    # ------------------------------------------------------------------
    @staticmethod
    async def test_fqgate() -> dict:
        from modules.stock.services import _fqgate

        result: dict[str, Any] = {"steps": []}

        async def _step(name: str, coro) -> Any:
            t0 = time.monotonic()
            try:
                data = await coro
                result["steps"].append({
                    "step": name, "ok": True,
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                })
                return data
            except Exception as exc:  # noqa: BLE001
                result["steps"].append({
                    "step": name, "ok": False, "error": str(exc)[:300],
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                })
                return None

        health = await _step("health", _fqgate.health())
        if health is not None:
            result["health"] = health

        from datetime import timedelta

        end = timezone.now().date()
        start = end - timedelta(days=10)
        bars = await _step(
            "daily_klines",
            _fqgate.fetch_daily_bars("600519", str(start), str(end)),
        )
        if bars:
            result["klines_sample"] = {"count": len(bars), "latest": bars[-1]}

        quotes = await _step("realtime_quote", _fqgate.fetch_spot_quotes(["600519"]))
        if quotes:
            result["quote_sample"] = quotes.get("600519")

        result["ok"] = all(s["ok"] for s in result["steps"]) and bool(result["steps"])
        return result


async def _get_config_row(db: AsyncSession, key: str) -> SysConfig | None:
    stmt = select(SysConfig).where(SysConfig.key == key)
    return (await db.execute(stmt)).scalar_one_or_none()


def _validate_config_patch(patch: dict) -> dict:
    if not patch:
        raise RequestError(msg=t("dataSource.empty_config"))
    cleaned: dict[str, Any] = {}
    for field, value in patch.items():
        rule = _CONFIG_RULES.get(field)
        if rule is None:
            raise RequestError(msg=t("dataSource.unknown_field", field=field))
        typ, lo, hi = rule
        if field == "circuit_mode":
            if value not in lo:
                raise RequestError(msg=t("dataSource.invalid_circuit_mode"))
            cleaned[field] = value
            continue
        if field == "enabled":
            cleaned[field] = bool(value)
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise RequestError(msg=t("dataSource.invalid_field", field=field)) from None
        if typ is int and num != int(num):
            raise RequestError(msg=t("dataSource.invalid_field", field=field))
        if num < lo or num > hi:
            raise RequestError(
                msg=t("dataSource.field_out_of_range", field=field, min=lo, max=hi)
            )
        cleaned[field] = int(num) if typ is int else num
    return cleaned
