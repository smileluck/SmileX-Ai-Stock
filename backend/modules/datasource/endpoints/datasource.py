#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据源管理相关接口
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import t
from core.response import ResponseModel, response_base
from database.db_manager import get_session
from modules.admin.deps.auth.permission import require_permission
from modules.admin.deps.auth.user_manager import current_user
from modules.datasource.schemas.datasource import (
    FqgateGatewayUpdate,
    SourceConfigUpdate,
)
from modules.datasource.services.datasource_service import DataSourceService

logger = logging.getLogger(__name__)

datasource_router = APIRouter(prefix="", tags=["系统管理/数据源管理"])


@datasource_router.get(
    "/list",
    response_model=ResponseModel[dict],
    summary="数据源列表：注册表 + 运行时状态（熔断/连续失败/最近错误）+ 今日用量 + 当前限流配置",
    dependencies=[Depends(require_permission("datasource:list"))],
)
async def list_sources(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    data = await DataSourceService.list_sources(db)
    return response_base.success(data=data)


@datasource_router.post(
    "/config/update",
    response_model=ResponseModel[dict],
    summary="更新单源限流/熔断配置（部分字段合并；circuit_mode 支持 auto/force_open/force_closed 手动熔断）",
    dependencies=[Depends(require_permission("datasource:config"))],
)
async def update_source_config(
    body: SourceConfigUpdate,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    merged = await DataSourceService.update_source_config(db, body.source, body.config)
    await db.commit()
    # 提交后立即刷新缓存，新配置不等下一个刷新周期
    from core.datasource.config import DataSourceConfigProvider

    await DataSourceConfigProvider.force_refresh()
    return response_base.success(data=merged, msg=t("dataSource.config_update_success"))


@datasource_router.post(
    "/fqgate/config",
    response_model=ResponseModel[dict],
    summary="更新 FQGate 网关连接配置（base_url）",
    dependencies=[Depends(require_permission("datasource:config"))],
)
async def update_fqgate_gateway(
    body: FqgateGatewayUpdate,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    data = await DataSourceService.update_fqgate_gateway(db, body.base_url)
    await db.commit()
    from core.datasource.config import DataSourceConfigProvider

    await DataSourceConfigProvider.force_refresh()
    return response_base.success(data=data, msg=t("dataSource.config_update_success"))


@datasource_router.get(
    "/stats",
    response_model=ResponseModel[list],
    summary="数据源用量统计（按小时聚合，默认近 7 天，最长 30 天）",
    dependencies=[Depends(require_permission("datasource:list"))],
)
async def get_stats(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    data = await DataSourceService.get_stats(db, days)
    return response_base.success(data=data)


@datasource_router.get(
    "/events",
    response_model=ResponseModel[list],
    summary="数据源最近失败事件（内存环形缓冲，进程重启清空）",
    dependencies=[Depends(require_permission("datasource:list"))],
)
async def get_events(
    source: str | None = Query(None, description="数据源标识，为空返回所有源"),
    user=Depends(current_user),
):
    data = await DataSourceService.get_events(source)
    return response_base.success(data=data)


@datasource_router.post(
    "/fqgate/test",
    response_model=ResponseModel[dict],
    summary="FQGate 连通性测试（health + 日K + 实时报价，逐步返回耗时与样本）",
    dependencies=[Depends(require_permission("datasource:test"))],
)
async def test_fqgate(user=Depends(current_user)):
    data = await DataSourceService.test_fqgate()
    return response_base.success(data=data)

