#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""数据源统一出站入口。

所有对外部数据源的调用经 call_external（同步 SDK）/ call_external_async（httpx 协程）
执行，统一获得：启用/熔断准入、并发与间隔限流、硬超时、用量统计、连续失败熔断。

用法（同步 SDK，如 akshare）::

    from core.datasource.gateway import call_external

    df = await call_external("eastmoney", ak.stock_zh_a_hist, symbol="600519", ...)

用法（异步协程，如 httpx）::

    from core.datasource.gateway import call_external_async

    resp = await call_external_async("fqgate", client.post, url, json=body)

同步调用经单源独立 ThreadPoolExecutor 执行（容量=max_concurrency），
不用 asyncio.to_thread 的共享默认池，避免源间互相挤占；
并发准入由单源信号量控制，超出并发的调用在信号量上排队等待。

被禁用/熔断时抛 DataSourceUnavailableError 子类，调用方按降级链处理；
超时统一转为 asyncio.TimeoutError；其余异常原样抛出。
"""
import asyncio
import logging
import time
from typing import Any, Callable

from core.datasource import stats, throttle
from core.datasource.config import DataSourceConfigProvider
from core.datasource.throttle import DataSourceUnavailableError  # noqa: F401（re-export）

logger = logging.getLogger(__name__)


async def _guarded(source: str, runner: Callable[[], Any], cfg: dict) -> Any:
    """准入 → 信号量 → 间隔 → 执行 → 统计/熔断记录"""
    try:
        throttle.check_available(source, cfg)
    except DataSourceUnavailableError as exc:
        stats.record(source, "rejected", 0, str(exc))
        raise

    semaphore = throttle.acquire_semaphore(source, cfg)
    async with semaphore:
        await throttle.wait_interval(source, cfg)
        t0 = time.monotonic()
        outcome = "success"
        try:
            return await asyncio.wait_for(runner(), timeout=float(cfg.get("timeout_s", 30)))
        except asyncio.TimeoutError:
            outcome = "timeout"
            raise
        except Exception:
            outcome = "fail"
            raise
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            if outcome == "success":
                stats.record(source, "success", latency_ms)
                throttle.record_success(source)
            else:
                err = "调用超时" if outcome == "timeout" else "调用失败"
                stats.record(source, outcome, latency_ms, err)
                triggered = throttle.record_failure(source, cfg)
                if triggered:
                    logger.warning("数据源 [%s] 已自动熔断", source)


async def call_external(source: str, fn: Callable, *args, **kwargs) -> Any:
    """同步函数（如 akshare/baostock SDK）经单源独立线程池执行，带统一限流与硬超时"""
    cfg = await DataSourceConfigProvider.get_source_config(source)
    executor = throttle.get_executor(source, cfg)
    loop = asyncio.get_running_loop()

    def runner():
        return loop.run_in_executor(
            executor, lambda: fn(*args, **kwargs)
        )

    return await _guarded(source, runner, cfg)


async def call_external_async(source: str, coro_fn: Callable, *args, **kwargs) -> Any:
    """协程函数（如 httpx.AsyncClient 方法）带统一限流与硬超时"""
    cfg = await DataSourceConfigProvider.get_source_config(source)

    async def runner():
        return await coro_fn(*args, **kwargs)

    return await _guarded(source, runner, cfg)
