from core.exception import setup_exception_handlers, setup_exception_global_handlers
from database.plugins import setup_soft_delete_plug
from fastapi import FastAPI
from core.middleware.share_middleware import RequestContextMiddleware
from core.middleware.security_middleware import (
    RequestAuditMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from core.middleware.operation_log_middleware import OperationLogMiddleware
from core.middleware.openapi_log_middleware import OpenapiLogMiddleware
from core.middleware.rate_limit_middleware import RateLimitMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from core.config import GlobalSetting


def setup_app(app: FastAPI, settings: GlobalSetting):
    """
    注册全局信息
    """

    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=settings.SECURITY.ALLOWED_HOSTS
    )

    # 配置跨域（允许其他服务访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.SECURITY.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestAuditMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(OperationLogMiddleware)
    app.add_middleware(OpenapiLogMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # 注册全局异常
    setup_exception_handlers(app)
    setup_exception_global_handlers(app)
    # 注册软删除插件
    setup_soft_delete_plug()
    # 注意：日志初始化（setup_logging）不在此时机调用——本函数在模块导入期执行，
    # uvicorn reload 父进程（python main.py）与 worker 子进程会各打开一份
    # logs/app.log 的轮转 handler，午夜双重轮转竞态会互相覆盖/删除归档。
    # 文件日志改在 main.lifespan 启动期配置（仅真正服务请求的进程）。
    # 预加载 i18n 文案目录（启动时加载一次，避免首请求时延迟）
    from core.i18n import load_catalogs, supported_locales

    load_catalogs()
    print(f"[OK] i18n 文案目录加载完成 | 支持语言: {supported_locales()}")
    # 加载插件
    if settings.PLUGINS.ENABLED:
        from plugins import load_plugins
        load_plugins(app, settings.PLUGINS.ENABLED)
