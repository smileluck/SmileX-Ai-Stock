#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MCP 服务管理 Schema"""

import re
from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field, field_validator

from modules.common.schemas.base import BaseReqEntity, BaseRespEntity, BoolField
from modules.common.schemas.page import PageRequest

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


def _validate_code(v: str) -> str:
    if not _CODE_RE.match(v):
        raise ValueError("服务编码仅支持小写字母开头的字母/数字/下划线，最长 50 字符")
    return v


def _validate_url(v: str) -> str:
    if not v.startswith(("http://", "https://")):
        raise ValueError("MCP 端点必须以 http:// 或 https:// 开头")
    return v


class McpServerQueryParams(PageRequest):
    """MCP 服务查询参数"""

    name: Optional[str] = Field(None, description="服务名称，支持模糊查询")
    code: Optional[str] = Field(None, description="服务编码，支持模糊查询")
    enabled: BoolField = Field(None, description="状态：True-启用，False-禁用")


class McpServerCreate(BaseReqEntity):
    """MCP 服务创建请求"""

    code: str = Field(..., description="服务编码（工具命名空间，创建后不可改）", min_length=1, max_length=50)
    name: str = Field(..., description="服务名称", min_length=1, max_length=100)
    url: str = Field(..., description="MCP 端点 URL（Streamable HTTP）", min_length=1, max_length=500)
    headers: Optional[dict] = Field(None, description="自定义请求头（JSON 对象）")
    enabled: bool = Field(True, description="是否启用")
    timeout_s: int = Field(30, description="调用超时（秒）", ge=1, le=300)
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    @field_validator("code")
    @classmethod
    def _code_ok(cls, v):
        return _validate_code(v)

    @field_validator("url")
    @classmethod
    def _url_ok(cls, v):
        return _validate_url(v)


class McpServerUpdate(BaseReqEntity):
    """MCP 服务更新请求（code 不可改）"""

    name: Optional[str] = Field(None, description="服务名称", min_length=1, max_length=100)
    url: Optional[str] = Field(None, description="MCP 端点 URL", max_length=500)
    headers: Optional[dict] = Field(None, description="自定义请求头（JSON 对象，传 null 清空）")
    enabled: BoolField = Field(None, description="是否启用")
    timeout_s: Optional[int] = Field(None, description="调用超时（秒）", ge=1, le=300)
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    @field_validator("url")
    @classmethod
    def _url_ok(cls, v):
        return _validate_url(v) if v is not None else v


class McpServerStatusUpdate(BaseReqEntity):
    """MCP 服务状态更新请求"""

    enabled: bool = Field(..., description="是否启用")


class McpServerResponseData(BaseRespEntity):
    """MCP 服务详细响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="服务ID")
    code: str = Field(..., description="服务编码")
    name: str = Field(..., description="服务名称")
    url: str = Field(..., description="MCP 端点 URL")
    headers: Optional[dict] = Field(None, description="自定义请求头")
    enabled: bool = Field(..., description="是否启用")
    timeout_s: int = Field(..., description="调用超时（秒）")
    remark: Optional[str] = Field(None, description="备注")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class McpServerTestResult(BaseReqEntity):
    """MCP 连通性测试结果（失败也走 success 包裹，由 success 字段区分）"""

    success: bool = Field(..., description="是否连接成功")
    latency_ms: int = Field(0, description="延迟（毫秒）")
    message: str = Field("", description="结果消息")
    tool_count: int = Field(0, description="工具数量")


class McpToolItem(BaseReqEntity):
    """MCP 工具描述"""

    name: str = Field(..., description="工具名")
    description: str = Field("", description="工具描述")
    input_schema: dict = Field(default_factory=dict, description="入参 JSON Schema")
