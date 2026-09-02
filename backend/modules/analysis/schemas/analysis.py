#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 大盘/板块分析相关 Schema
"""
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, BeforeValidator

# 分析类型常量（菜单页与执行记录共用）
ANALYSIS_TYPES = ("market", "sector", "news", "rotation")

ANALYSIS_TYPE_NAMES = {
    "market": "大盘分析",
    "sector": "板块分析",
    "news": "每日资讯分析",
    "rotation": "轮动策略分析",
}

# 分析时段常量（close-收盘分析 16:05，morning-早盘分析 9:20，weekly-周日晚周度复盘）
SESSION_TYPES = ("close", "morning", "weekly")

SESSION_TYPE_NAMES = {
    "close": "收盘分析",
    "morning": "早盘分析",
    "weekly": "周度复盘",
}

# 类型×时段合法组合（news 仅支持 morning/weekly；market/sector 仅支持 close/morning；
# rotation 仅 close——轮动规律需完整收盘数据，可手动随时触发）
VALID_TYPE_SESSIONS = {
    "market": ("close", "morning"),
    "sector": ("close", "morning"),
    "news": ("morning", "weekly"),
    "rotation": ("close",),
}

# query 参数解析：空串/非法值一律归为 None（不回退默认值，避免筛选静默吞记录）
AnalysisTypeQuery = Annotated[
    Optional[str],
    BeforeValidator(lambda v: v if v in ANALYSIS_TYPES else None),
]

AnalysisSessionQuery = Annotated[
    Optional[str],
    BeforeValidator(lambda v: v if v in SESSION_TYPES else None),
]


class AnalysisRunItem(BaseModel):
    """分析执行记录项（列表用，不含报告原文）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_type: str
    session: str = "close"  # close-收盘分析，morning-早盘分析
    run_date: str
    trigger_type: str
    status: str  # running-执行中，success-成功，failed-失败
    parsed_result: Optional[dict] = None
    error_msg: Optional[str] = None
    created_at: Optional[datetime] = None


class AnalysisRunDetailItem(AnalysisRunItem):
    """分析执行记录详情（含 AI 报告原文）"""

    ai_raw_response: Optional[str] = None


class AnalysisRunSubmitResult(BaseModel):
    """分析提交结果（异步执行：接口立即返回，结果见执行记录）"""

    run_id: int
    status: str = "running"


class AnalysisConfigItem(BaseModel):
    """分析策略配置项（无配置记录时返回默认值，data 始终非空）"""

    model_config = ConfigDict(from_attributes=True)

    analysis_type: str
    session: str = "close"
    prompt_template: Optional[str] = None
    include_tomorrow: bool = True
    tomorrow_prompt_template: Optional[str] = None
    updated_at: Optional[datetime] = None


class AnalysisConfigUpdateRequest(BaseModel):
    """分析策略配置保存请求"""

    prompt_template: Optional[str] = Field(
        None, max_length=2000,
        description="分析策略定制提示词（关注面/风格/风控偏好等，空则使用默认策略）",
    )
    include_tomorrow: bool = Field(True, description="是否包含明日研判章节")
    tomorrow_prompt_template: Optional[str] = Field(
        None, max_length=2000,
        description="明日研判定制提示词（方法论与侧重点，空则使用内置专业研判框架）",
    )
