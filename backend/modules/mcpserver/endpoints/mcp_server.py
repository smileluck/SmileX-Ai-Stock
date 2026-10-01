#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP 服务管理相关接口
"""
import logging
from typing import List

from fastapi import APIRouter, Depends

from core.i18n import t
from core.response.response_schema import ResponseModel, ResponsePageModel, response_base
from database.db_manager import get_session
from database.models.sys.user import SysUser
from modules.admin.deps.auth.permission import require_permission
from modules.admin.deps.auth.user_manager import current_user
from modules.common.schemas.page import PageRequest, get_page_params, get_paginated_results
from modules.mcpserver.schemas.mcp_server import (
    McpServerCreate,
    McpServerQueryParams,
    McpServerResponseData,
    McpServerStatusUpdate,
    McpServerTestResult,
    McpServerUpdate,
    McpToolItem,
)
from modules.mcpserver.services.mcp_server_service import McpServerService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

mcp_server_router = APIRouter(
    prefix="", tags=["环境配置/MCP服务管理"], dependencies=[Depends(current_user)]
)


@mcp_server_router.get(
    "/list",
    response_model=ResponsePageModel[McpServerResponseData],
    summary="MCP 服务列表（分页）",
    dependencies=[Depends(require_permission("mcp:list"))],
)
async def get_mcp_server_list(
    query_params: McpServerQueryParams = Depends(),
    page_params: PageRequest = Depends(get_page_params),
    db: AsyncSession = Depends(get_session),
):
    query = McpServerService.build_query(query_params)
    page_data = await get_paginated_results(
        db=db,
        page_params=page_params,
        query=query,
        schema=McpServerResponseData,
    )
    return response_base.page(data=page_data)


@mcp_server_router.post(
    "/add",
    response_model=ResponseModel[McpServerResponseData],
    summary="创建 MCP 服务",
    dependencies=[Depends(require_permission("mcp:manage"))],
)
async def create_mcp_server(
    server_in: McpServerCreate,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    server = await McpServerService.create_server(db, server_in)
    return response_base.success(
        data=McpServerResponseData.model_validate(server), msg=t("common.create_success")
    )


@mcp_server_router.put(
    "/{server_id}",
    response_model=ResponseModel[McpServerResponseData],
    summary="更新 MCP 服务（code 不可改）",
    dependencies=[Depends(require_permission("mcp:manage"))],
)
async def update_mcp_server(
    server_id: int,
    server_in: McpServerUpdate,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    server = await McpServerService.update_server(db, server_id, server_in)
    return response_base.success(
        data=McpServerResponseData.model_validate(server), msg=t("common.update_success")
    )


@mcp_server_router.put(
    "/{server_id}/status",
    response_model=ResponseModel[McpServerResponseData],
    summary="启用/禁用 MCP 服务",
    dependencies=[Depends(require_permission("mcp:manage"))],
)
async def update_mcp_server_status(
    server_id: int,
    body: McpServerStatusUpdate,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    server = await McpServerService.update_status(db, server_id, body.enabled)
    return response_base.success(
        data=McpServerResponseData.model_validate(server), msg=t("common.status_update_success")
    )


@mcp_server_router.delete(
    "/{server_id}",
    response_model=ResponseModel,
    summary="删除 MCP 服务",
    dependencies=[Depends(require_permission("mcp:manage"))],
)
async def delete_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    await McpServerService.delete_server(db, server_id)
    return response_base.success(msg=t("common.delete_success"))


@mcp_server_router.post(
    "/{server_id}/test",
    response_model=ResponseModel[McpServerTestResult],
    summary="MCP 连通性测试（initialize + tools/list，失败由 data.success 区分）",
    dependencies=[Depends(require_permission("mcp:test"))],
)
async def test_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    result = await McpServerService.test_server(db, server_id)
    return response_base.success(data=result)


@mcp_server_router.get(
    "/{server_id}/tools",
    response_model=ResponseModel[List[McpToolItem]],
    summary="获取 MCP 服务的工具列表（实时向 server 查询）",
    dependencies=[Depends(require_permission("mcp:test"))],
)
async def get_mcp_server_tools(
    server_id: int,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    tools = await McpServerService.list_server_tools(db, server_id)
    return response_base.success(data=tools)
