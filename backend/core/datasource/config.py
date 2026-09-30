#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""数据源限流/熔断动态配置提供器。

从 SysConfig 表读取 datasource.* 配置项（group=network，type=json），
内存缓存 30 秒，与 RateLimitConfigProvider 同一模式：
缓存失效由面板配置更新或 system.refresh_rate_limit_config 定时任务触发，
未落库的源使用 DEFAULT_SOURCE_CONFIGS 默认值。
"""
import json
import logging
import time
from typing import Any

from database.models.sys.config import ConfigGroup

logger = logging.getLogger(__name__)

# 每源默认配置；未落库时生效。字段说明：
#   enabled: 是否启用（False 时该源所有调用直接拒绝，降级链跳过）
#   max_concurrency: 最大并发
#   min_interval_ms: 同一源两次调用的最小间隔
#   timeout_s: 单次调用硬超时（asyncio.wait_for）
#   failure_threshold: 连续失败达到该次数自动熔断
#   cooldown_s: 自动熔断后的冷却秒数（期间调用直接拒绝）
#   circuit_mode: auto-自动熔断 / force_open-手动熔断 / force_closed-手动强制可用
DEFAULT_SOURCE_CONFIGS: dict[str, dict[str, Any]] = {
    # 东财 push2his 对高频请求 IP 级断连，并发与间隔从严
    "eastmoney": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 300,
                  "timeout_s": 30, "failure_threshold": 5, "cooldown_s": 300, "circuit_mode": "auto"},
    "sina": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 200,
             "timeout_s": 15, "failure_threshold": 5, "cooldown_s": 120, "circuit_mode": "auto"},
    # baostock 是全局单连接协议，必须串行；整批上限 120s
    "baostock": {"enabled": True, "max_concurrency": 1, "min_interval_ms": 0,
                 "timeout_s": 120, "failure_threshold": 3, "cooldown_s": 600, "circuit_mode": "auto"},
    # FQGate 本机网关，官方前端并发 4、服务端预算 30s
    "fqgate": {"enabled": True, "max_concurrency": 4, "min_interval_ms": 100,
               "timeout_s": 32, "failure_threshold": 5, "cooldown_s": 60, "circuit_mode": "auto"},
    "tencent": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 500,
                "timeout_s": 15, "failure_threshold": 5, "cooldown_s": 300, "circuit_mode": "auto"},
    # 同花顺板块列表/成分股为整批多页同步函数（单次网关调用），超时需覆盖整批
    "ths": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 500,
            "timeout_s": 180, "failure_threshold": 3, "cooldown_s": 300, "circuit_mode": "auto"},
    "xueqiu": {"enabled": True, "max_concurrency": 1, "min_interval_ms": 500,
               "timeout_s": 30, "failure_threshold": 5, "cooldown_s": 300, "circuit_mode": "auto"},
    "cls": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 300,
            "timeout_s": 10, "failure_threshold": 5, "cooldown_s": 120, "circuit_mode": "auto"},
    "wscn": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 300,
             "timeout_s": 10, "failure_threshold": 5, "cooldown_s": 120, "circuit_mode": "auto"},
    "yicai": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 300,
              "timeout_s": 10, "failure_threshold": 5, "cooldown_s": 120, "circuit_mode": "auto"},
    "jin10": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 300,
              "timeout_s": 10, "failure_threshold": 5, "cooldown_s": 120, "circuit_mode": "auto"},
    "futu": {"enabled": True, "max_concurrency": 2, "min_interval_ms": 300,
             "timeout_s": 10, "failure_threshold": 5, "cooldown_s": 120, "circuit_mode": "auto"},
}

_CONFIG_KEY_PREFIX = "datasource."
# FQGate 网关自身连接配置（base_url 等），与限流配置分键存储
FQGATE_CONFIG_KEY = "datasource.fqgate_gateway"
FQGATE_DEFAULTS: dict[str, Any] = {"base_url": "http://127.0.0.1:17281"}

_DEFAULT = {"enabled": True, "max_concurrency": 2, "min_interval_ms": 200,
            "timeout_s": 30, "failure_threshold": 5, "cooldown_s": 300, "circuit_mode": "auto"}


class DataSourceConfigProvider:
    _cache: dict[str, Any] = {}
    _expire_at: float = 0.0
    TTL = 30

    @classmethod
    async def get_source_config(cls, source: str) -> dict[str, Any]:
        """取单源配置：库值覆盖默认值，缺失字段回落默认"""
        await cls._ensure_cache()
        merged = dict(DEFAULT_SOURCE_CONFIGS.get(source, _DEFAULT))
        stored = cls._cache.get(f"{_CONFIG_KEY_PREFIX}{source}")
        if isinstance(stored, dict):
            merged.update(stored)
        return merged

    @classmethod
    async def get_fqgate_gateway(cls) -> dict[str, Any]:
        """FQGate 网关连接配置（base_url 等）"""
        await cls._ensure_cache()
        stored = cls._cache.get(FQGATE_CONFIG_KEY)
        merged = dict(FQGATE_DEFAULTS)
        if isinstance(stored, dict):
            merged.update(stored)
        return merged

    @classmethod
    async def get_all(cls) -> dict[str, Any]:
        await cls._ensure_cache()
        return dict(cls._cache)

    @classmethod
    def invalidate(cls) -> None:
        cls._expire_at = 0.0

    @classmethod
    async def _ensure_cache(cls) -> None:
        # 与 RateLimitConfigProvider 一致：调用路径上不回源，
        # 缓存由 system.refresh_rate_limit_config 定时任务（25s）刷新，
        # 未刷新前使用 DEFAULT_SOURCE_CONFIGS 默认值
        if time.time() < cls._expire_at:
            return
        logger.debug("DataSourceConfigProvider 缓存已过期，等待后台定时任务刷新")

    @classmethod
    async def force_refresh(cls) -> None:
        try:
            await cls._refresh()
        except Exception as exc:
            logger.error("DataSourceConfigProvider 刷新失败: %s", exc)
            # 刷新失败保留旧缓存并短暂退避，避免每调用都回源
            cls._expire_at = time.time() + 5

    @classmethod
    async def _refresh(cls) -> None:
        from database import get_session
        from sqlalchemy import select
        from database.models.sys.config import SysConfig

        cache: dict[str, Any] = {}
        async for db in get_session():
            stmt = (
                select(SysConfig)
                .where(SysConfig.group == ConfigGroup.NETWORK)
                .where(SysConfig.key.startswith(_CONFIG_KEY_PREFIX))
            )
            result = await db.execute(stmt)
            for row in result.scalars().all():
                try:
                    cache[row.key] = json.loads(row.value)
                except (ValueError, TypeError):
                    logger.warning("数据源配置解析失败，忽略 key=%s", row.key)
            break

        cls._cache = cache
        cls._expire_at = time.time() + cls.TTL
