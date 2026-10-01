#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""外部 MCP 服务（Streamable HTTP）薄封装。

短连接模型：每次操作（list_tools / call_tool）建立一次会话，完成后关闭。
不做连接池/长驻会话——MCP server 配置动态可改，短连接语义最简单可靠。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)

# 单个工具结果文本截断上限（防止超大结果撑爆 LLM 上下文）
MAX_RESULT_CHARS = 8000


@dataclass
class McpToolInfo:
    """MCP 工具描述（tools/list 单项）"""

    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)


@dataclass
class McpServerTools:
    """initialize + tools/list 结果"""

    tools: list[McpToolInfo] = field(default_factory=list)
    instructions: Optional[str] = None
    server_name: str = ""
    server_version: str = ""


@dataclass
class McpCallResult:
    """tools/call 结果：文本拼接 + 结构化内容"""

    text: str
    structured: Optional[Any] = None
    is_error: bool = False


async def _with_session(
    url: str,
    headers: Optional[dict],
    timeout_s: int,
    fn,
):
    """建立短会话并执行 fn(session, init_result)，统一超时控制。"""
    async def _run():
        async with streamablehttp_client(url, headers=headers, timeout=timeout_s) as (read, write, _):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                return await fn(session, init_result)

    return await asyncio.wait_for(_run(), timeout=timeout_s)


async def list_tools(url: str, headers: Optional[dict] = None, timeout_s: int = 30) -> McpServerTools:
    """获取 MCP server 工具列表（含 initialize 的 instructions/serverInfo）。"""

    async def _list(session: ClientSession, init_result):
        result = await session.list_tools()
        tools = [
            McpToolInfo(
                name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema or {},
            )
            for t in result.tools
        ]
        server_info = getattr(init_result, "serverInfo", None)
        return McpServerTools(
            tools=tools,
            instructions=getattr(init_result, "instructions", None),
            server_name=getattr(server_info, "name", "") if server_info else "",
            server_version=getattr(server_info, "version", "") if server_info else "",
        )

    return await _with_session(url, headers, timeout_s, _list)


async def call_tool(
    url: str,
    tool_name: str,
    arguments: dict,
    headers: Optional[dict] = None,
    timeout_s: int = 30,
) -> McpCallResult:
    """调用 MCP 工具，返回拼接文本（截断）与结构化内容。"""

    async def _call(session: ClientSession, _init):
        return await session.call_tool(tool_name, arguments or {})

    try:
        result = await _with_session(url, headers, timeout_s, _call)
    except asyncio.TimeoutError:
        logger.warning(f"MCP 工具调用超时 | tool={tool_name} url={url} timeout={timeout_s}s")
        raise
    except Exception as e:
        logger.warning(f"MCP 工具调用失败 | tool={tool_name} url={url} err={e}")
        raise

    parts: list[str] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        else:
            parts.append(str(block))
    text = "\n".join(parts)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n...[结果过长已截断]"

    return McpCallResult(
        text=text,
        structured=getattr(result, "structuredContent", None),
        is_error=bool(getattr(result, "isError", False)),
    )
