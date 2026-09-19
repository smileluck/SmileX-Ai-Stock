#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
调度器 leader 选举锁（MySQL GET_LOCK）

多 worker（gunicorn）部署时每个进程都会执行 lifespan，但只允许一个进程运行
APScheduler。MySQL 5.7+ 的命名锁同名全局唯一、持锁连接断开时自动释放，
正好提供选主 + 故障转移语义：

- 抢到锁（GET_LOCK 返回 1）的进程成为 leader，回调 on_acquire 启动调度器
- 未抢到锁的进程不启动调度器，后台周期性重试抢锁（leader 宕机后接管）
- leader 周期性 ping 持锁连接保活；ping 失败说明连接断开（锁已被 MySQL
  自动释放），本地回调 on_lose 停掉调度器后重新进入抢锁循环

持锁连接为专用 AsyncConnection，从业务 engine 检出后独占持有，绝不归还池、
不与业务 session 混用。pool_recycle 只在连接检出时生效，不影响已检出的持锁
连接；ping 间隔必须远小于 MySQL wait_timeout（默认 28800s），防止持锁连接
被服务端闲置断开导致锁意外释放。
"""

import asyncio
import inspect
import logging
import os
from typing import Awaitable, Callable, Optional, Union

from sqlalchemy.ext.asyncio import AsyncConnection

from database.manager.async_manager import async_db_manager

logger = logging.getLogger(__name__)

LOCK_NAME = "smilex_scheduler_leader"
PING_INTERVAL_SECONDS = 20
RETRY_INTERVAL_SECONDS = 15

Callback = Callable[[], Union[None, Awaitable[None]]]


class SchedulerLeaderLock:
    """基于 MySQL GET_LOCK 的调度器选主锁"""

    def __init__(
        self,
        on_acquire: Callback,
        on_lose: Callback,
        lock_name: str = LOCK_NAME,
        ping_interval: float = PING_INTERVAL_SECONDS,
        retry_interval: float = RETRY_INTERVAL_SECONDS,
    ):
        self._on_acquire = on_acquire
        self._on_lose = on_lose
        self._lock_name = lock_name
        self._ping_interval = ping_interval
        self._retry_interval = retry_interval
        self._conn: Optional[AsyncConnection] = None
        self._is_leader = False
        self._stopped = False
        self._standby_logged = False
        self._lockless_logged = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    async def start(self) -> bool:
        """启动选主，返回本进程当前是否为 leader。

        先同步抢一次锁：抢到则立即执行 on_acquire（启动调度器），回调异常会
        释放锁并向上抛出（等同调度器启动失败，阻止应用启动）；未抢到则由后台
        任务周期性重试，抢到后再执行 on_acquire。
        """
        if self._task is not None:
            return self._is_leader
        self._stopped = False
        if await self._try_acquire():
            try:
                await self._become_leader()
            except Exception:
                await self._lose_leader(notify=False)
                raise
        self._task = asyncio.create_task(self._run(), name="scheduler-leader-lock")
        return self._is_leader

    async def stop(self) -> None:
        """停止选主：取消后台任务，释放锁并关闭持锁连接"""
        self._stopped = True
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # 后台任务被取消时其 finally 已尝试释放，这里兜底保证锁一定释放
        await self._lose_leader()

    async def _run(self) -> None:
        """后台循环：leader 保活 ping / follower 重试抢锁"""
        try:
            while not self._stopped:
                if self._is_leader:
                    try:
                        await asyncio.sleep(self._ping_interval)
                        # 非 MySQL 退化模式没有持锁连接，无需保活 ping
                        if self._conn is not None:
                            await self._conn.exec_driver_sql("SELECT 1")
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error("调度器 leader 锁保活 ping 失败，失去 leader 身份: %s", exc)
                        await self._lose_leader()
                else:
                    await asyncio.sleep(self._retry_interval)
                    if self._stopped:
                        break
                    if await self._try_acquire():
                        try:
                            await self._become_leader()
                        except Exception as exc:
                            logger.error("抢到调度器 leader 锁后启动回调失败，释放锁等待重试: %s", exc)
                            await self._lose_leader(notify=False)
        except asyncio.CancelledError:
            raise
        finally:
            await self._lose_leader()

    async def _try_acquire(self) -> bool:
        """用专用连接执行 GET_LOCK，抢到返回 True 并持有连接"""
        engine = async_db_manager.engine
        if engine is None:
            logger.warning("数据库连接池未初始化，暂无法抢调度器 leader 锁，稍后重试")
            return False
        if engine.dialect.name != "mysql":
            # 非 MySQL（如本地 dev 的 PostgreSQL）无 GET_LOCK：退化为不选主直接
            # 成为 leader，行为与改动前一致；生产 MySQL 不受影响
            if not self._lockless_logged:
                logger.info(
                    "当前数据库为 %s，不支持 MySQL GET_LOCK 选主，本进程直接作为调度器 leader 运行",
                    engine.dialect.name,
                )
                self._warn_if_lockless_multi_worker()
                self._lockless_logged = True
            self._conn = None
            return True
        conn: Optional[AsyncConnection] = None
        try:
            conn = await engine.connect()
            result = await conn.exec_driver_sql("SELECT GET_LOCK(%s, 0)", (self._lock_name,))
            acquired = result.scalar() == 1
        except Exception as exc:
            logger.warning("抢调度器 leader 锁失败，稍后重试: %s", exc)
            if conn is not None:
                try:
                    await conn.close()
                except Exception as close_exc:
                    logger.warning("关闭抢锁失败的连接异常: %s", close_exc)
            return False
        if not acquired:
            try:
                await conn.close()
            except Exception as exc:
                logger.warning("关闭未抢到锁的连接异常: %s", exc)
            if not self._standby_logged:
                # 待机日志只在状态切换时记一次，避免重试循环每 15s 刷屏
                logger.info("未抢到调度器 leader 锁（另一进程持有），本进程不启动调度器，将周期性重试")
                self._standby_logged = True
            return False
        self._conn = conn
        self._standby_logged = False
        return True

    @staticmethod
    def _warn_if_lockless_multi_worker() -> None:
        """lockless（非 MySQL）模式无选主能力：gunicorn 多 worker 时每个进程
        都会当 leader 重复执行定时任务，检测到时打 WARNING 提示风险"""
        if "gunicorn" not in os.environ.get("SERVER_SOFTWARE", "").lower():
            return
        raw = os.environ.get("GUNICORN_WORKERS")
        try:
            # 未设置时与 backend/gunicorn.conf.py 的默认值 4 保持一致
            workers = int(raw) if raw else 4
        except ValueError:
            workers = 4
        if workers > 1:
            logger.warning(
                "非 MySQL 数据库无法选主，且 gunicorn workers=%d > 1：定时任务将在每个 "
                "worker 进程重复执行。请改用 MySQL 或将 GUNICORN_WORKERS 设为 1",
                workers,
            )

    async def _become_leader(self) -> None:
        self._is_leader = True
        logger.info("已抢到调度器 leader 锁，本进程成为调度器 leader")
        await self._run_callback(self._on_acquire)

    async def _lose_leader(self, notify: bool = True) -> None:
        """释放 leader 身份：先停调度器（on_lose），再 RELEASE_LOCK 并关闭连接。

        幂等：未持锁且非 leader 时直接返回。
        """
        was_leader = self._is_leader
        conn = self._conn
        self._is_leader = False
        self._conn = None
        if not was_leader and conn is None:
            return
        if was_leader:
            logger.info("释放调度器 leader 身份")
            if notify:
                try:
                    await self._run_callback(self._on_lose)
                except Exception as exc:
                    logger.error("失去调度器 leader 身份的回调执行异常: %s", exc)
        if conn is not None:
            try:
                await conn.exec_driver_sql("SELECT RELEASE_LOCK(%s)", (self._lock_name,))
            except Exception as exc:
                logger.warning("释放调度器 leader 锁失败（连接可能已断开，锁将由 MySQL 自动释放）: %s", exc)
            try:
                await conn.close()
            except Exception as exc:
                logger.warning("关闭调度器 leader 锁专用连接失败: %s", exc)

    @staticmethod
    async def _run_callback(callback: Callback) -> None:
        result = callback()
        if inspect.isawaitable(result):
            await result
