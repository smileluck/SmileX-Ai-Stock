#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Skills 管理 Schema"""

import re
from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field, field_validator

from modules.common.schemas.base import BaseReqEntity, BaseRespEntity, BoolField
from modules.common.schemas.page import PageRequest

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


def _validate_code(v: str) -> str:
    if not _CODE_RE.match(v):
        raise ValueError("技能编码仅支持小写字母开头的字母/数字/下划线，最长 50 字符")
    return v


class SkillQueryParams(PageRequest):
    """技能查询参数"""

    name: Optional[str] = Field(None, description="技能名称，支持模糊查询")
    code: Optional[str] = Field(None, description="技能编码，支持模糊查询")
    status: BoolField = Field(None, description="状态：True-启用，False-禁用")


class SkillCreate(BaseReqEntity):
    """技能创建请求"""

    code: str = Field(..., description="技能编码（唯一标识，创建后不可改）", min_length=1, max_length=50)
    name: str = Field(..., description="技能名称", min_length=1, max_length=100)
    content: str = Field(..., description="技能指令内容（启用后注入 Agent 系统提示词）", min_length=1)
    description: Optional[str] = Field(None, description="技能描述", max_length=500)
    status: bool = Field(True, description="状态：True-启用，False-禁用")
    sort: int = Field(0, description="排序（注入提示词的优先级，越小越靠前）", ge=0, le=9999)

    @field_validator("code")
    @classmethod
    def _code_ok(cls, v):
        return _validate_code(v)


class SkillUpdate(BaseReqEntity):
    """技能更新请求（code 不可改）"""

    name: Optional[str] = Field(None, description="技能名称", min_length=1, max_length=100)
    content: Optional[str] = Field(None, description="技能指令内容", min_length=1)
    description: Optional[str] = Field(None, description="技能描述", max_length=500)
    status: BoolField = Field(None, description="状态：True-启用，False-禁用")
    sort: Optional[int] = Field(None, description="排序（越小越靠前）", ge=0, le=9999)


class SkillStatusUpdate(BaseReqEntity):
    """技能状态更新请求"""

    status: bool = Field(..., description="状态：True-启用，False-禁用")


class SkillResponseData(BaseRespEntity):
    """技能详细响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="技能ID")
    code: str = Field(..., description="技能编码")
    name: str = Field(..., description="技能名称")
    content: str = Field(..., description="技能指令内容")
    description: Optional[str] = Field(None, description="技能描述")
    status: bool = Field(..., description="状态：True-启用，False-禁用")
    sort: int = Field(..., description="排序")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
