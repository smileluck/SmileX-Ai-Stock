#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""数据源出站节流与熔断。

每个数据源独立一组运行时状态：
- 并发信号量（容量随配置变化自动重建）
- 最小调用间隔（last_call 时间戳 + sleep 补齐）
- 熔断器：auto 模式连续失败达标自动断开 cooldown_s；
  force_open 手动熔断 / force_closed 强制可用（面板控制）

熔断/禁用态下调用抛出 DataSourceUnavailableError 子类，
各 fetcher 现有降级链的 try/except 会自然接住并转入下一源。
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class DataSourceUnavailableError(Exception):
    """数据源当前不可用（被禁用或熔断中），调用方应降级到下一源"""


class DataSourceDisabledError(DataSourceUnavailableError):
    """数据源被禁用"""


class DataSourceCircuitOpenError(DataSourceUnavailableError):
    """数据源熔断中"""


@dataclass
class SourceThrottle:
    """单源运行时状态"""

    semaphore: asyncio.Semaphore | None = None
    semaphore_size: int = 0
    last_call_at: float = 0.0
    consecutive_failures: int = 0
    circuit_opened_until: float = 0.0  # monotonic 时间戳，0 表示未熔断
    interval_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_throttles: dict[str, SourceThrottle] = {}


def _throttle(source: str) -> SourceThrottle:
    t = _throttles.get(source)
    if t is None:
        t = _throttles[source] = SourceThrottle()
    return t


def check_available(source: str, cfg: dict) -> None:
    """准入检查：禁用/熔断态直接抛异常，不产生外呼"""
    if not cfg.get("enabled", True):
        raise DataSourceDisabledError(f"数据源 [{source}] 已被禁用")
    mode = cfg.get("circuit_mode", "auto")
    if mode == "force_open":
        raise DataSourceCircuitOpenError(f"数据源 [{source}] 已被手动熔断")
    if mode == "force_closed":
        return
    t = _throttle(source)
    if t.circuit_opened_until > time.monotonic():
        remain = int(t.circuit_opened_until - time.monotonic())
        raise DataSourceCircuitOpenError(
            f"数据源 [{source}] 熔断中（连续失败 {t.consecutive_failures} 次，{remain}s 后恢复）"
        )


def acquire_semaphore(source: str, cfg: dict) -> asyncio.Semaphore:
    """取单源信号量，配置容量变化时重建"""
    size = max(1, int(cfg.get("max_concurrency", 2)))
    t = _throttle(source)
    if t.semaphore is None or t.semaphore_size != size:
        t.semaphore = asyncio.Semaphore(size)
        t.semaphore_size = size
    return t.semaphore


async def wait_interval(source: str, cfg: dict) -> None:
    """保证同源两次调用间隔不低于 min_interval_ms（串行化时间戳更新）"""
    interval = float(cfg.get("min_interval_ms", 0)) / 1000.0
    if interval <= 0:
        return
    t = _throttle(source)
    async with t.interval_lock:
        delay = t.last_call_at + interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        t.last_call_at = time.monotonic()


def record_success(source: str) -> None:
    t = _throttle(source)
    t.consecutive_failures = 0
    if t.circuit_opened_until:
        t.circuit_opened_until = 0.0
        logger.info("数据源 [%s] 调用成功，熔断恢复", source)


def record_failure(source: str, cfg: dict) -> bool:
    """记录失败，auto 模式下连续失败达标则熔断；返回本次是否触发熔断"""
    t = _throttle(source)
    t.consecutive_failures += 1
    if cfg.get("circuit_mode", "auto") != "auto":
        return False
    threshold = max(1, int(cfg.get("failure_threshold", 5)))
    if t.consecutive_failures >= threshold and not t.circuit_opened_until:
        cooldown = max(1, int(cfg.get("cooldown_s", 300)))
        t.circuit_opened_until = time.monotonic() + cooldown
        logger.warning(
            "数据源 [%s] 连续失败 %d 次，自动熔断 %ds",
            source, t.consecutive_failures, cooldown,
        )
        return True
    return False


def circuit_state(source: str, cfg: dict) -> str:
    """面板展示用：closed / open / half_open（自动熔断冷却中）"""
    mode = cfg.get("circuit_mode", "auto")
    if mode == "force_open":
        return "open"
    if mode == "force_closed":
        return "closed"
    t = _throttle(source)
    if t.circuit_opened_until > time.monotonic():
        return "half_open"
    return "closed"


def runtime_state(source: str) -> dict:
    """面板展示用：连续失败数与熔断恢复剩余秒数"""
    t = _throttle(source)
    remain = t.circuit_opened_until - time.monotonic()
    return {
        "consecutive_failures": t.consecutive_failures,
        "circuit_recover_in_s": max(0, int(remain)) if remain > 0 else 0,
    }


def reset_runtime(source: str) -> None:
    """手动解除熔断/清空失败计数（面板操作或配置保存后调用）"""
    t = _throttle(source)
    t.consecutive_failures = 0
    t.circuit_opened_until = 0.0
