#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 推荐股票相关 Schema
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# 推荐方向常量
DIRECTION_LIMIT_UP = "limit_up"  # 涨停候选
DIRECTION_BOTTOM_FISH = "bottom_fish"  # 抄底
RECOMMEND_DIRECTIONS = (DIRECTION_LIMIT_UP, DIRECTION_BOTTOM_FISH)

# 建仓方式常量（与 business_strategy_signal.entry_type 一致）
ENTRY_MARKET = "market"  # 按实时价直接成交
ENTRY_LIMIT = "limit"  # 触及买点才成交

# 六维度小结论字段（reasons JSON 固定键）
REASON_DIMENSIONS = ("news", "sentiment", "factor", "sector_fund", "main_force", "limit_up")


class RecommendStockItem(BaseModel):
    """推荐个股项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    rank: int
    stock_code: str
    stock_name: str
    direction: str = Field(..., description="推荐方向：limit_up-涨停候选，bottom_fish-抄底")
    score: float = Field(..., description="综合评分 0-100")
    buy_price: Optional[float] = Field(None, description="预判买点（参考买价）")
    target_price: Optional[float] = Field(None, description="目标价（预估卖点）")
    stop_loss_price: Optional[float] = Field(None, description="止损价")
    entry_type: str = Field("market", description="建仓方式：market-直接成交，limit-触及买点才成交")
    reasons: Optional[dict] = Field(None, description="六维度小结论")
    summary: Optional[str] = Field(None, description="一句话推荐逻辑")
    signal_id: Optional[int] = Field(None, description="关联的策略买入信号 ID")


class RecommendRunItem(BaseModel):
    """推荐执行记录项（列表用，不含 AI 原文与候选池快照）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_date: date
    trigger_type: str
    status: str = Field(..., description="执行状态：running-执行中，success-成功，failed-失败")
    parsed_result: Optional[dict] = None
    error_msg: Optional[str] = None
    strategy_id: Optional[int] = None
    created_at: Optional[datetime] = None


class RecommendRunDetailItem(RecommendRunItem):
    """推荐执行记录详情（含 AI 原文、候选池快照与推荐个股列表）"""

    ai_raw_response: Optional[str] = None
    candidate_snapshot: Optional[dict] = None
    stocks: list[RecommendStockItem] = []


class RecommendRunSubmitResult(BaseModel):
    """推荐提交结果（异步执行：接口立即返回，结果见执行记录）"""

    run_id: int
    status: str = "running"
