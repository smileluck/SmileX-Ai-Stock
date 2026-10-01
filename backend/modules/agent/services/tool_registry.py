"""
Agent 工具注册表 —— 声明式注册工具函数，供 LLM 通过 Function Calling 调用。

使用方式:
    @register_tool(
        name="get_hot_stocks",
        description="获取当前股票热榜 Top N",
        parameters={...JSON Schema...},
    )
    async def get_hot_stocks(db: AsyncSession, limit: int = 10) -> dict:
        ...

注册后自动出现在 tool_registry.get_openai_format() 中，LLM 可自主决定是否调用。
执行时由 tool_registry.execute(name, arguments, db) 分派到具体函数。
"""

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """工具定义。"""

    name: str
    description: str
    parameters: dict  # JSON Schema
    func: Callable[..., Awaitable[Any]] = field(repr=False)


_REGISTRY: dict[str, ToolDefinition] = {}

# 动态工具（外部 MCP server 工具，每次对话前由 mcp_tools.register_mcp_tools 重建）
_DYNAMIC: dict[str, ToolDefinition] = {}


def register_tool(
    name: str, description: str, parameters: dict
) -> Callable:
    """装饰器：注册一个工具函数。"""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        if name in _REGISTRY:
            logger.warning("工具 [%s] 已注册，将被覆盖", name)
        _REGISTRY[name] = ToolDefinition(
            name=name, description=description, parameters=parameters, func=func
        )
        logger.debug("注册工具: %s", name)
        return func

    return decorator


def register_dynamic_tool(
    name: str, description: str, parameters: dict, func: Callable[..., Awaitable[Any]]
) -> None:
    """注册一个动态工具（外部 MCP server 工具）。"""
    if name in _REGISTRY:
        logger.warning("动态工具 [%s] 与内置工具重名，跳过", name)
        return
    _DYNAMIC[name] = ToolDefinition(
        name=name, description=description, parameters=parameters, func=func
    )
    logger.debug("注册动态工具: %s", name)


def clear_dynamic_tools() -> None:
    """清空动态工具（每次对话前重建）。"""
    _DYNAMIC.clear()


def get_openai_format() -> list[dict]:
    """返回所有已注册工具（内置 + 动态）的 OpenAI Function Calling 格式描述。"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in (*_REGISTRY.values(), *_DYNAMIC.values())
    ]


async def execute(
    name: str, arguments: dict[str, Any], db: AsyncSession
) -> dict:
    """
    执行指定工具，返回结果字典。

    工具函数的第一个参数固定为 db: AsyncSession（由框架注入），
    其余参数从 arguments 中按名映射。

    异常会被捕获并转为 {"error": ...}，保证 LLM 能收到错误反馈而不是中断对话。
    """
    tool = _REGISTRY.get(name) or _DYNAMIC.get(name)
    if not tool:
        logger.warning("未注册的工具: %s", name)
        return {"error": f"工具 {name} 不存在"}

    # 过滤出函数实际接受的参数（排除 db）；
    # 动态工具（MCP 闭包）签名为 (db, **kwargs)，透传全部参数
    sig = inspect.signature(tool.func)
    has_var_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if has_var_kwargs:
        valid_params = {k: v for k, v in arguments.items() if k != "db"}
    else:
        valid_params = {
            k: v
            for k, v in arguments.items()
            if k in sig.parameters and k != "db"
        }

    try:
        result = await tool.func(db, **valid_params)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as e:
        logger.exception("工具 [%s] 执行异常", name)
        return {"error": f"工具执行异常: {e}"}
