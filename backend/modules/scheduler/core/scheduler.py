#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
APScheduler 封装管理器
负责调度器生命周期、任务同步、执行包装
"""

import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import ConflictingIdError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.scheduler.core.registry import get_task_definition, get_task_definition_by_path
from database.models.sys.scheduled_task import SysScheduledTask
from database.models.sys.task_log import SysScheduledTaskLog
from database.utils.timezone import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

# 进程内 per-task 执行互斥锁：key=task.id。同一任务的手动触发与 cron tick
# 并发时后到者直接跳过，防止任务副作用（建仓/LLM 分析等）被并发执行两次
_task_execution_locks: dict[int, asyncio.Lock] = {}

# 周期性全量 resync 的内置 job id：直接注册在 APScheduler 上（不入库），
# 让 follower worker 上对任务表的 CRUD 能传播到 leader 进程的调度器。
# sync_jobs_from_db 会保留该 job，避免全量同步时把自己删掉
RESYNC_JOB_ID = "__scheduler_db_resync__"
RESYNC_INTERVAL_SECONDS = 60


class SchedulerManager:
    """调度器管理器（单例）"""

    _instance = None

    def __init__(self):
        # 固定调度器时区为应用时区（DEFAULT_TIMEZONE=Asia/Shanghai）。否则 cron 表达式会按
        # 服务器本地时区解释，部署到 UTC 服务器时整体偏移 8 小时。
        self._scheduler = AsyncIOScheduler(
            timezone=ZoneInfo(DEFAULT_TIMEZONE),
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 60,
            },
        )

    @classmethod
    def get_instance(cls) -> "SchedulerManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("定时任务调度器已启动")

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("定时任务调度器已停止")

    async def sync_jobs_from_db(self, db: AsyncSession):
        """从数据库同步任务到 APScheduler（保留 RESYNC_JOB_ID 等进程内内置 job）"""
        for job in self._scheduler.get_jobs():
            if job.id != RESYNC_JOB_ID:
                self._scheduler.remove_job(job.id)

        stmt = select(SysScheduledTask).where(
            SysScheduledTask.status == True,  # noqa: E712
            SysScheduledTask.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        tasks = result.scalars().all()

        synced = 0
        for task in tasks:
            try:
                self._add_job_from_task(task)
                task.next_run_at = self._get_job_next_run(str(task.id))
                synced += 1
            except Exception as exc:
                logger.error("同步任务 %s 失败: %s", task.task_key, exc)

        await db.commit()
        logger.info("已同步 %d/%d 个定时任务", synced, len(tasks))

    async def add_task_job(self, task: SysScheduledTask):
        """添加单个任务到调度器"""
        job_id = str(task.id)
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass
        if task.status:
            self._add_job_from_task(task)
            task.next_run_at = self._get_job_next_run(job_id)
        else:
            task.next_run_at = None

    def remove_task_job(self, task_id: int):
        """从调度器移除任务"""
        try:
            self._scheduler.remove_job(str(task_id))
        except Exception:
            pass

    async def run_task_now(self, task: SysScheduledTask, db: AsyncSession, triggered_by: str = "manual"):
        """手动触发任务执行"""
        definition = get_task_definition(task.task_key) or (
            get_task_definition_by_path(task.function_path) if task.function_path else None
        )
        func = definition.function if definition else _load_function(task.function_path)
        if func is None:
            logger.error("任务 %s 的函数无法加载", task.task_key)
            return

        await _execute_task(task, func, db, triggered_by=triggered_by)

    def enable_periodic_resync(self, interval_seconds: int = RESYNC_INTERVAL_SECONDS):
        """注册周期性全量 resync job（幂等，replace_existing）。

        leader 只在启动时 sync 一次的话，follower worker 上对任务表的
        创建/修改/启停只写 DB，leader 的 APScheduler 永远感知不到；
        该内置 job 周期性重放 DB -> 调度器的全量同步。调度器停止时
        （失去 leader 身份/进程退出）job 随之消失，无需额外清理。
        """
        self._scheduler.add_job(
            _resync_jobs_wrapper,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=RESYNC_JOB_ID,
            name="scheduler:db-resync",
            replace_existing=True,
        )
        logger.info("已注册周期性任务同步 job（每 %ds 全量 resync）", interval_seconds)

    def trigger_task_in_background(self, task_id: int) -> bool:
        """把任务投递到调度器后台立即执行（fire-and-forget），不阻塞调用方。

        手动触发接口用它而非 run_task_now：HTTP 请求立即返回，
        任务在后台用独立 session 执行，不受请求生命周期影响。

        job id 固定为 manual-{task_id}：排队中的重复触发撞 ConflictingIdError
        返回 False；但 DateTrigger 是一次性的，执行开始 job id 就空出，所以
        执行中的去重要靠 per-task 锁——任务正在执行时直接返回 False
        （不替换、不排队第二个），配合 max_instances=1 与 _execute_task 的
        per-task 锁保证手动触发与 cron tick 不并发。
        """
        if not self.running:
            logger.warning("调度器未运行，无法后台触发任务 task_id=%s", task_id)
            return False
        lock = _task_execution_locks.get(task_id)
        if lock is not None and lock.locked():
            logger.warning("任务 task_id=%s 正在执行中，拒绝重复手动触发", task_id)
            return False
        try:
            self._scheduler.add_job(
                _manual_job_wrapper,
                trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
                args=[task_id],
                id=f"manual-{task_id}",
                name=f"manual:{task_id}",
            )
        except ConflictingIdError:
            logger.warning("任务 task_id=%s 已有手动触发在排队中，忽略本次重复触发", task_id)
            return False
        return True

    @staticmethod
    def preview_cron(cron_expression: str, count: int = 5) -> list[str]:
        """预览 cron 表达式接下来 N 次执行时间"""
        try:
            trigger = CronTrigger.from_crontab(cron_expression, timezone=ZoneInfo(DEFAULT_TIMEZONE))
            now = datetime.now(timezone.utc)
            times = []
            prev = None
            for _ in range(count):
                next_time = trigger.get_next_fire_time(prev, now)
                if next_time is None:
                    break
                times.append(next_time.isoformat())
                prev = next_time
                now = next_time
            return times
        except Exception as exc:
            logger.warning("Cron 表达式预览失败: %s", exc)
            return []

    def _add_job_from_task(self, task: SysScheduledTask):
        """从数据库任务记录创建 APScheduler job"""
        trigger = self._build_trigger(task)
        if trigger is None:
            return

        job_id = str(task.id)

        self._scheduler.add_job(
            _scheduled_job_wrapper,
            trigger=trigger,
            id=job_id,
            args=[task.id],
            name=task.name,
            replace_existing=True,
        )

    def _build_trigger(self, task: SysScheduledTask):
        """根据 trigger_type 构建对应的 APScheduler trigger"""
        try:
            if task.trigger_type == "cron":
                return CronTrigger.from_crontab(task.cron_expression, timezone=ZoneInfo(DEFAULT_TIMEZONE))
            if task.trigger_type == "interval":
                params = json.loads(task.trigger_params or "{}")
                return IntervalTrigger(**params)
            if task.trigger_type == "date":
                params = json.loads(task.trigger_params or "{}")
                return DateTrigger(**params)
        except Exception as exc:
            logger.error("构建触发器失败 %s: %s", task.task_key, exc)
        return None

    def _get_job_next_run(self, job_id: str) -> datetime | None:
        """获取 job 的下次执行时间"""
        try:
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                return job.next_run_time
        except Exception:
            pass
        return None


async def _resync_jobs_wrapper():
    """周期性全量 resync job 入口：独立 session，失败只记日志不中断调度器"""
    from database.manager.async_manager import get_session

    try:
        async for db in get_session():
            await SchedulerManager.get_instance().sync_jobs_from_db(db)
    except Exception as exc:
        logger.error("周期性同步定时任务失败（下一轮将重试）: %s", exc)


async def _manual_job_wrapper(task_id: int):
    """手动触发任务的后台执行入口：独立 session，不受请求生命周期影响"""
    from database.manager.async_manager import get_session

    async for db in get_session():
        try:
            stmt = select(SysScheduledTask).where(
                SysScheduledTask.id == task_id,
                SysScheduledTask.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()
            if task is None:
                logger.error("手动触发失败：任务 task_id=%s 不存在", task_id)
                return

            definition = get_task_definition(task.task_key) or (
                get_task_definition_by_path(task.function_path) if task.function_path else None
            )
            func = definition.function if definition else _load_function(task.function_path)
            if func is None:
                logger.error("任务 %s 的函数无法加载", task.task_key)
                return

            await _execute_task(task, func, db, triggered_by="manual")
        except Exception as exc:
            logger.error("手动触发任务执行异常 task_id=%s: %s", task_id, exc)
            await db.rollback()


async def _scheduled_job_wrapper(task_id: int):
    """APScheduler 调用的 job 入口"""
    from database.manager.async_manager import get_session

    async for db in get_session():
        try:
            stmt = select(SysScheduledTask).where(
                SysScheduledTask.id == task_id,
                SysScheduledTask.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()
            if task is None or not task.status:
                return

            definition = get_task_definition(task.task_key) or (
                get_task_definition_by_path(task.function_path) if task.function_path else None
            )
            func = definition.function if definition else _load_function(task.function_path)
            if func is None:
                logger.error("任务 %s 的函数无法加载", task.task_key)
                return

            await _execute_task(task, func, db, triggered_by="scheduler")

            # 执行完毕后更新下次执行时间
            manager = SchedulerManager.get_instance()
            task.next_run_at = manager._get_job_next_run(str(task_id))
            await db.commit()
        except Exception as exc:
            logger.error("定时任务执行异常 task_id=%s: %s", task_id, exc)
            await db.rollback()


async def _execute_task(
    task: SysScheduledTask,
    func,
    db: AsyncSession,
    triggered_by: str = "scheduler",
):
    """任务执行入口：进程内 per-task 串行化后委托 _do_execute_task。

    手动触发（_manual_job_wrapper）与 cron tick（_scheduled_job_wrapper）都经
    这里；同一任务并发触发时后到者直接跳过（不执行、不写 running 日志记录）。
    """
    lock = _task_execution_locks.setdefault(task.id, asyncio.Lock())
    if lock.locked():
        logger.warning(
            "任务 %s (task_id=%s) 正在执行中，跳过本次 %s 触发",
            task.task_key, task.id, triggered_by,
        )
        return
    async with lock:
        await _do_execute_task(task, func, db, triggered_by=triggered_by)


async def _do_execute_task(
    task: SysScheduledTask,
    func,
    db: AsyncSession,
    triggered_by: str = "scheduler",
):
    """执行单个任务：创建日志 -> 执行 -> 更新状态"""
    from database.utils.timezone import timezone as tz

    now = tz.now()
    log = SysScheduledTaskLog(
        task_id=task.id,
        task_name=task.name,
        task_key=task.task_key,
        status="running",
        start_time=now,
        triggered_by=triggered_by,
    )
    db.add(log)

    task.last_status = "running"
    task.last_run_at = now
    await db.commit()

    definition = get_task_definition(task.task_key) or (
        get_task_definition_by_path(task.function_path) if task.function_path else None
    )
    params_model = None
    if definition and definition.params_schema and task.params:
        try:
            params_model = definition.params_schema.model_validate(task.params)
        except Exception as exc:
            end = tz.now()
            log.status = "failed"
            log.end_time = end
            log.duration_ms = (end - now).total_seconds() * 1000
            log.error_message = f"参数校验失败: {exc}"[:5000]
            task.last_status = "failed"
            await db.commit()
            logger.error("定时任务 %s 参数校验失败: %s", task.task_key, exc)
            return

    try:
        if params_model is not None:
            coro = func(params=params_model)
        else:
            coro = func()
        if task.timeout > 0:
            result = await asyncio.wait_for(coro, timeout=task.timeout)
        else:
            result = await coro

        end = tz.now()
        duration = (end - now).total_seconds() * 1000

        result_str = None
        if result is not None:
            try:
                result_str = json.dumps(result, ensure_ascii=False, default=str)[:5000]
            except (TypeError, ValueError):
                result_str = str(result)[:5000]

        log.status = "success"
        log.end_time = end
        log.duration_ms = duration
        log.result = result_str

        task.last_status = "success"
        await db.commit()

    except asyncio.TimeoutError:
        end = tz.now()
        log.status = "timeout"
        log.end_time = end
        log.duration_ms = (end - now).total_seconds() * 1000
        log.error_message = f"任务执行超时（{task.timeout}秒）"
        task.last_status = "timeout"
        await db.commit()

    except Exception as exc:
        end = tz.now()
        log.status = "failed"
        log.end_time = end
        log.duration_ms = (end - now).total_seconds() * 1000
        log.error_message = traceback.format_exc()[:5000]
        task.last_status = "failed"
        await db.commit()
        logger.error("定时任务 %s 执行失败: %s", task.task_key, exc)


def _load_function(function_path: str | None):
    """动态加载函数"""
    if not function_path:
        return None
    try:
        import importlib

        module_path, func_name = function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except Exception as exc:
        logger.error("加载函数 %s 失败: %s", function_path, exc)
        return None
