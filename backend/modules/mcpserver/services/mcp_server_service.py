#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MCP 服务管理 Service"""

import logging
import time

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from core.exception.errors import ConflictError, NotFoundError
from core.i18n import t
from core.mcp import client as mcp_client
from database.models.sys.mcp_server import SysMcpServer
from modules.mcpserver.schemas.mcp_server import (
    McpServerCreate,
    McpServerQueryParams,
    McpServerTestResult,
    McpServerUpdate,
    McpToolItem,
)

logger = logging.getLogger(__name__)


class McpServerService:
    """MCP 服务管理"""

    @staticmethod
    def build_query(query_params: McpServerQueryParams) -> Select:
        """构建分页查询"""
        base_query = select(SysMcpServer)
        conditions = []
        if query_params.name:
            conditions.append(SysMcpServer.name.contains(query_params.name))
        if query_params.code:
            conditions.append(SysMcpServer.code.contains(query_params.code))
        if query_params.enabled is not None:
            conditions.append(SysMcpServer.enabled == query_params.enabled)
        if conditions:
            base_query = base_query.where(and_(*conditions))
        return base_query.order_by(SysMcpServer.id.desc())

    @staticmethod
    async def get_server(db: AsyncSession, server_id: int) -> SysMcpServer:
        """获取单个服务"""
        result = await db.execute(select(SysMcpServer).where(SysMcpServer.id == server_id))
        server = result.scalar_one_or_none()
        if not server:
            raise NotFoundError(msg=t("mcpServer.not_found", id=server_id))
        return server

    @staticmethod
    async def create_server(db: AsyncSession, server_in: McpServerCreate) -> SysMcpServer:
        """创建服务配置"""
        result = await db.execute(
            select(SysMcpServer).where(SysMcpServer.code == server_in.code)
        )
        if result.scalar_one_or_none():
            raise ConflictError(msg=t("mcpServer.code_exist"))

        server = SysMcpServer(
            code=server_in.code,
            name=server_in.name,
            url=server_in.url,
            headers=server_in.headers,
            enabled=server_in.enabled,
            timeout_s=server_in.timeout_s,
            remark=server_in.remark,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        logger.info("创建 MCP 服务成功，ID: %d，编码: %s", server.id, server.code)
        return server

    @staticmethod
    async def update_server(
        db: AsyncSession, server_id: int, server_in: McpServerUpdate
    ) -> SysMcpServer:
        """更新服务配置（code 不可改）"""
        server = await McpServerService.get_server(db, server_id)

        update_data = server_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(server, field, value)

        await db.commit()
        await db.refresh(server)
        logger.info("更新 MCP 服务成功，ID: %d", server_id)
        return server

    @staticmethod
    async def update_status(db: AsyncSession, server_id: int, enabled: bool) -> SysMcpServer:
        """启用/禁用服务"""
        server = await McpServerService.get_server(db, server_id)
        server.enabled = enabled
        await db.commit()
        await db.refresh(server)
        logger.info("更新 MCP 服务状态成功，ID: %d，enabled: %s", server_id, enabled)
        return server

    @staticmethod
    async def delete_server(db: AsyncSession, server_id: int) -> bool:
        """删除服务配置"""
        server = await McpServerService.get_server(db, server_id)
        await db.delete(server)
        await db.commit()
        logger.info("删除 MCP 服务成功，ID: %d", server_id)
        return True

    @staticmethod
    async def list_enabled(db: AsyncSession) -> list[SysMcpServer]:
        """获取所有启用的服务（Agent 动态工具注册用）"""
        result = await db.execute(
            select(SysMcpServer).where(SysMcpServer.enabled == True)  # noqa: E712
        )
        return list(result.scalars().all())

    @staticmethod
    async def test_server(db: AsyncSession, server_id: int) -> McpServerTestResult:
        """连通性测试：initialize + tools/list，返回耗时与工具数"""
        server = await McpServerService.get_server(db, server_id)
        start = time.monotonic()
        try:
            server_tools = await mcp_client.list_tools(server.url, server.headers, server.timeout_s)
        except Exception as e:
            return McpServerTestResult(
                success=False,
                latency_ms=int((time.monotonic() - start) * 1000),
                message=str(e),
            )
        return McpServerTestResult(
            success=True,
            latency_ms=int((time.monotonic() - start) * 1000),
            message="ok",
            tool_count=len(server_tools.tools),
        )

    @staticmethod
    async def list_server_tools(db: AsyncSession, server_id: int) -> list[McpToolItem]:
        """获取服务的工具列表"""
        server = await McpServerService.get_server(db, server_id)
        server_tools = await mcp_client.list_tools(server.url, server.headers, server.timeout_s)
        return [
            McpToolItem(name=t.name, description=t.description, input_schema=t.input_schema)
            for t in server_tools.tools
        ]
