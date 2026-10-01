#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""外部 MCP server 工具动态注册。

每次 Agent 对话前调用 register_mcp_tools(db)：
- 查询 sys_mcp_server 中启用的 server
- 拉取 tools/list（进程内 TTL 缓存，避免每轮对话都打满 MCP server）
- 注册为动态工具，命名 mcp__<code>__<工具名>（去掉与 code 重复的前缀）
- 单个 server 不可用只跳过该 server，不阻塞对话

返回各 server 的 instructions（外部数据源使用规则），由 agent_service
拼进 system prompt。
"""

import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.mcp import client as mcp_client
from core.mcp.client import McpToolInfo
from database.models.sys.mcp_server import SysMcpServer
from modules.agent.services.tool_registry import (
    clear_dynamic_tools,
    register_dynamic_tool,
)

logger = logging.getLogger(__name__)

# tools/list 进程内缓存 TTL（秒）
_TOOLS_CACHE_TTL = 300

# code -> (过期时间戳, McpServerTools)
_tools_cache: dict[str, tuple[float, Any]] = {}


def _short_tool_name(code: str, tool_name: str) -> str:
    """去掉与 server code 重复的前缀：fqgate + fqgate_market_klines -> market_klines"""
    prefix = f"{code}_"
    if tool_name.startswith(prefix):
        return tool_name[len(prefix):]
    return tool_name


def _make_call_func(server: SysMcpServer, tool_name: str):
    """生成动态工具执行闭包。签名 (db, **kwargs)：db 由框架注入后忽略。"""

    async def _call(db: AsyncSession, **kwargs):  # noqa: ARG001
        result = await mcp_client.call_tool(
            server.url,
            tool_name,
            kwargs,
            headers=server.headers,
            timeout_s=server.timeout_s,
        )
        data: dict[str, Any] = {"text": result.text}
        if result.structured is not None:
            data["structured"] = result.structured
        if result.is_error:
            data["is_error"] = True
        return data

    return _call


async def _get_server_tools(server: SysMcpServer):
    """带 TTL 缓存的 tools/list。缓存键含 url/updated_at，配置变更即失效。"""
    cache_key = server.code
    cached = _tools_cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    server_tools = await mcp_client.list_tools(server.url, server.headers, server.timeout_s)
    _tools_cache[cache_key] = (time.monotonic() + _TOOLS_CACHE_TTL, server_tools)
    return server_tools


async def register_mcp_tools(db: AsyncSession) -> list[str]:
    """注册所有启用 MCP server 的工具，返回各 server 的 instructions 列表。"""
    from modules.mcpserver.services.mcp_server_service import McpServerService

    clear_dynamic_tools()

    try:
        servers = await McpServerService.list_enabled(db)
    except Exception:
        logger.exception("查询启用的 MCP server 失败，跳过动态工具注册")
        return []

    instructions: list[str] = []
    for server in servers:
        try:
            server_tools = await _get_server_tools(server)
        except Exception as e:
            logger.warning("MCP server [%s] 工具拉取失败，跳过: %s", server.code, e)
            continue

        tool: McpToolInfo
        for tool in server_tools.tools:
            name = f"mcp__{server.code}__{_short_tool_name(server.code, tool.name)}"
            description = f"[{server.name}] {tool.description}".strip()
            register_dynamic_tool(
                name=name,
                description=description,
                parameters=tool.input_schema or {"type": "object", "properties": {}},
                func=_make_call_func(server, tool.name),
            )

        if server_tools.instructions:
            instructions.append(f"【{server.name}】{server_tools.instructions}")

        logger.info(
            "MCP server [%s] 注册 %d 个动态工具", server.code, len(server_tools.tools)
        )

    return instructions
