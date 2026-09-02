#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
项目入口文件
初始化FastAPI应用并注册各个模块
"""
from contextlib import asynccontextmanager
from typing import Union
import asyncio
from fastapi import FastAPI
from core.config import settings  # 导入配置
from logging import getLogger
from database.db_manager import init_pool, close_pool
from database.manager.async_manager import get_session
from core.redis import RedisPool

from modules.app.router import router as app_app_router
from modules.admin.router import router as admin_app_router
from modules.openapi.router import open_router
from modules.stock.router import router as stock_router
from modules.agent.router import router as agent_router
from modules.strategy.router import router as strategy_router
from modules.analysis.router import router as analysis_router
from modules.macro.router import router as macro_router
from modules.financial.router import router as financial_router
from modules.research.router import router as research_router
from modules.demo.router import router as demo_router
from modules.admin.endpoints.sys.health import health_router
from core.registry.setup_registry import setup_app
from core.websocket import FastAPIConnectionManager, set_connection_manager

logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    # 初始化数据库连接池
    logger.info("初始化数据库连接池")
    await init_pool()
    logger.info("数据库连接池初始化完成")
    # 初始化 Redis 连接池
    logger.info("初始化 Redis 连接池")
    await RedisPool.init_pool()
    logger.info("Redis 连接池初始化完成")
    # 初始化 WebSocket 连接管理器
    logger.info("初始化 WebSocket 连接管理器")
    connection_manager = FastAPIConnectionManager()
    app.state.connection_manager = connection_manager
    set_connection_manager(connection_manager)
    logger.info("WebSocket 连接管理器初始化完成")
    # 预热 IP 黑名单到 Redis（非致命：预热失败会自动从 DB 回源，限流仍可用）
    try:
        from modules.admin.services.sys.rate_limit_service import RateLimitService
        count = await RateLimitService.warmup_blacklist()
        logger.info("IP 黑名单预热数量: %s", count)
    except Exception as exc:
        # 保留 try/except + ERROR 日志 + 结构化字段，便于告警系统识别「启动降级」事件
        logger.error(
            "IP 黑名单预热异常，限流功能降级运行: %s",
            exc,
            extra={"event": "startup_degraded", "component": "ip_blacklist"},
        )
    # 启动定时任务调度器（核心业务：异步导出/限流配置同步/内置任务，失败必须阻止启动）
    from modules.scheduler.core.scheduler import SchedulerManager
    import modules.scheduler.tasks.builtin  # noqa: F401
    import modules.scheduler.tasks.rate_limit_config  # noqa: F401
    import modules.scheduler.tasks.generic  # noqa: F401
    import modules.scheduler.tasks.export_task  # noqa: F401
    import modules.scheduler.tasks.news_sync  # noqa: F401
    import modules.scheduler.tasks.stock_hot_sync  # noqa: F401
    import modules.scheduler.tasks.stock_market_sync  # noqa: F401
    import modules.scheduler.tasks.stock_constituent_sync  # noqa: F401
    import modules.scheduler.tasks.stock_block_trade_sync  # noqa: F401
    import modules.scheduler.tasks.strategy_run  # noqa: F401
    import modules.scheduler.tasks.analysis_run  # noqa: F401
    import modules.scheduler.tasks.macro_sync  # noqa: F401
    import modules.scheduler.tasks.financial_run  # noqa: F401
    import modules.scheduler.tasks.research_sync  # noqa: F401
    import modules.scheduler.tasks.rotation_sync  # noqa: F401

    manager = SchedulerManager.get_instance()
    manager.start()
    app.state.scheduler_manager = manager
    # 种子数据：菜单 + 同步装饰器注册的任务（非致命：缺失只影响菜单可见性）
    # 必须先 seed 再从 DB 同步 job：否则新注册的任务在首次入库的这次启动中
    # 只写 DB、不进调度器，要等到下一次重启才会真正按 cron 触发
    try:
        from modules.scheduler.seed import seed_scheduler
        async for db_seed in get_session():
            await seed_scheduler(db_seed)
    except Exception as exc:
        # 降级为 WARNING：不影响核心功能，ERROR 会污染 5xx 错误率统计
        logger.warning("定时任务种子数据加载失败，部分预置任务可能缺失: %s", exc)
    async for db_sync in get_session():
        await manager.sync_jobs_from_db(db_sync)
    logger.info("定时任务同步完成")
    yield
    # 停止定时任务调度器
    try:
        from modules.scheduler.core.scheduler import SchedulerManager
        SchedulerManager.get_instance().stop()
    except Exception as exc:
        logger.error("定时任务调度器停止异常: %s", exc)
    # 关闭 Redis 连接池
    logger.info("关闭 Redis 连接池")
    await RedisPool.close_pool()
    logger.info("Redis 连接池已关闭")
    # 关闭数据库连接池
    logger.info("关闭数据库连接池")
    await close_pool()
    logger.info("数据库连接池已关闭")


app = FastAPI(
    title=settings.SERVICE.NAME,
    description="这是一个使用FastAPI构建的示例API",
    version="1.0.0",
    contact={
        "name": "SpatialtemporalAI",
        "url": "https://github.com/orgs/SpatialtemporalAI/dashboard",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    docs_url=None if settings.ENVIR == "prod" and not settings.SERVICE.OPENAPI_ENABLE_IN_PROD else "/docs",
    redoc_url=None if settings.ENVIR == "prod" and not settings.SERVICE.OPENAPI_ENABLE_IN_PROD else "/redoc",
    openapi_url=None if settings.ENVIR == "prod" and not settings.SERVICE.OPENAPI_ENABLE_IN_PROD else "/openapi.json",
)
# 配置app
setup_app(app, settings=settings)
logger.info("配置文件初始化完成")

# 挂载子应用
# app.mount("/admin", admin_app)
# app.mount("/app", app_app)
# 挂载认证路由
app.include_router(app_app_router)
app.include_router(admin_app_router)
# A股行情模块
app.include_router(stock_router)
# AI Agent 模块（SSE 流式对话 + 工具调用）
app.include_router(agent_router)
# AI 分析策略模块（策略定制 + 定时执行 + 模拟盘跟踪）
app.include_router(strategy_router)
# AI 大盘/板块分析模块（异步生成 + 历史回看 + 收盘后定时生成）
app.include_router(analysis_router)
# AI 宏观指数模块（中美 CPI/PPI/M1/M2 等 + 注入 AI 分析）
app.include_router(macro_router)
# AI 财报解读模块（财报抓取 + 解读预测）
app.include_router(financial_router)
# AI 研报中心模块（券商研报采集 + 概览统计 + 供策略分析）
app.include_router(research_router)
# 示例模块（akshare / Baostock SDK 简单调用演示）
app.include_router(demo_router)
# 开放API（商户 HMAC 签名鉴权）
app.include_router(open_router)
# 健康/就绪探针：顶级路由，无鉴权，不受任何业务中间件约束
app.include_router(health_router)


if __name__ == "__main__":
    """
    主函数，用于直接运行应用
    添加Ctrl+C监听，实现优雅退出
    """
    import signal
    import uvicorn

    # 定义信号处理函数
    def signal_handler(signum, frame):
        """
        信号处理函数，用于处理Ctrl+C信号
        """
        logger.info("收到退出信号，正在优雅关闭应用...")
        # 这里不需要手动调用关闭函数，因为lifespan会处理
        # 我们只需要记录日志，让uvicorn正常关闭即可

    # 注册信号处理函数
    signal.signal(signal.SIGINT, signal_handler)  # 处理Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 处理kill命令

    # 运行应用
    logger.info("启动应用...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
