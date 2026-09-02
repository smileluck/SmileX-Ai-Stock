#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""企业财报 AI 解读相关 Schema"""
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, BeforeValidator, Field


def _norm_query_code(v) -> Optional[str]:
    """股票代码 query 参数：空串/非法归 None"""
    if not v or not isinstance(v, str):
        return None
    digits = "".join(ch for ch in v if ch.isdigit())
    return digits.zfill(6) if digits else None


StockCodeQuery = Annotated[Optional[str], BeforeValidator(_norm_query_code)]

_RATING_VALUES = {"优秀", "良好", "一般", "较差"}
_DIRECTION_VALUES = {"改善", "持平", "恶化"}


def _norm_choice(values: set[str]):
    def _norm(v) -> Optional[str]:
        """枚举 query 参数：空串/非法归 None"""
        if not v or not isinstance(v, str):
            return None
        v = v.strip()
        return v if v in values else None

    return _norm


RatingQuery = Annotated[Optional[str], BeforeValidator(_norm_choice(_RATING_VALUES))]
DirectionQuery = Annotated[Optional[str], BeforeValidator(_norm_choice(_DIRECTION_VALUES))]


class FinancialReportItem(BaseModel):
    """财报关键指标记录"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_code: str
    stock_name: Optional[str] = None
    report_period: str
    metrics: Optional[dict] = None
    fetched_at: Optional[datetime] = None


class ResearchBrief(BaseModel):
    """每股最新一条券商研报摘要（盈利预测对照）"""

    org_name: Optional[str] = None
    rating: Optional[str] = None
    published_date: Optional[str] = None
    forecast: Optional[dict] = None  # {年份: {eps, pe}}


class FinancialInterpretItem(BaseModel):
    """财报解读记录项（列表用，不含报告原文）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_code: str
    stock_name: Optional[str] = None
    industry: Optional[str] = None
    report_period: Optional[str] = None
    run_date: str
    trigger_type: str
    status: str  # running / success / failed
    parsed_result: Optional[dict] = None
    research_brief: Optional[ResearchBrief] = None
    error_msg: Optional[str] = None
    created_at: Optional[datetime] = None


class FinancialInterpretDetailItem(FinancialInterpretItem):
    """财报解读详情（含 AI 报告原文）"""

    ai_raw_response: Optional[str] = None


class FinancialInterpretSubmitResult(BaseModel):
    """解读提交结果（异步执行：接口立即返回，结果见解读记录）"""

    interpretation_id: int
    status: str = "running"


class FinancialConfigItem(BaseModel):
    """财报解读分析策略配置（prompt 为空则使用内置默认策略）"""

    model_config = ConfigDict(from_attributes=True)

    prompt_template: Optional[str] = None
    updated_at: Optional[datetime] = None


class FinancialConfigUpdateRequest(BaseModel):
    """分析策略保存请求（prompt 为空表示恢复默认策略）"""

    prompt_template: Optional[str] = Field(default=None, max_length=2000)
