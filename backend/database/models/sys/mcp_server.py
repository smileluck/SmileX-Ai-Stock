#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""外部 MCP 服务配置表：存储 MCP server 连接配置（Agent 动态工具来源）。"""

from typing import Optional

from sqlalchemy import String, Boolean, Integer, JSON
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class SysMcpServer(Base):
    """
    外部 MCP 服务配置表
    存储外部 MCP server（Streamable HTTP）连接配置，启用的 server 工具
    在 Agent 对话时动态注册进工具表（命名空间 mcp__<code>__<tool>）
    """

    # 服务编码（唯一，小写字母/数字/下划线，作工具命名空间）
    code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False, comment="服务编码（工具命名空间）"
    )
    # 服务名称
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="服务名称")
    # MCP 端点（Streamable HTTP）
    url: Mapped[str] = mapped_column(String(500), nullable=False, comment="MCP 端点 URL")
    # 请求头（如 Authorization），JSON 对象
    headers: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None, comment="自定义请求头（JSON 对象）"
    )
    # 是否启用
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    # 调用超时（秒）
    timeout_s: Mapped[int] = mapped_column(Integer, default=30, comment="调用超时（秒）")
    # 备注
    remark: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="备注"
    )
