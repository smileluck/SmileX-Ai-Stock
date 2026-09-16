#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略回测相关 Schema
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode

# 回测状态常量
BACKTEST_STATUS = ("running", "success", "failed")

# 回测区间上限（年）
MAX_BACKTEST_YEARS = 3


class BacktestRunRequest(BaseModel):
    """发起回测请求"""

    strategy_id: int = Field(..., description="策略 ID")
    start_date: str = Field(..., description="回测开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="回测结束日期 YYYY-MM-DD")
    initial_capital: float = Field(1000000, gt=0, description="初始资金（元）")
    slippage_pct: float = Field(
        0.1, ge=0, le=50,
        description="滑点参数：fixed 模式为滑点比例(%)（≤10）；amp 模式为振幅系数（≤50，10=振幅的10%）",
    )
    slippage_model: Literal["fixed", "amp"] = Field(
        "fixed", description="滑点模型：fixed-固定百分比，amp-振幅比例"
    )
    commission_pct: float = Field(0.025, ge=0, le=10, description="佣金比例(%)，最低 5 元")
    stamp_tax_pct: float = Field(0.05, ge=0, le=10, description="印花税比例(%)，仅卖出收取")

    @model_validator(mode="after")
    def _check_slippage(self):
        if self.slippage_model == "fixed" and self.slippage_pct > 10:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg=f"fixed 模式滑点比例不能超过 10%，实际 {self.slippage_pct}",
            )
        if self.slippage_model == "amp" and self.slippage_pct > 50:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg=f"amp 模式振幅系数不能超过 50，实际 {self.slippage_pct}",
            )
        return self

    @field_validator("start_date", "end_date")
    @classmethod
    def _check_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg=f"日期格式非法: {v}，应为 YYYY-MM-DD",
            )
        return v


class BacktestItem(BaseModel):
    """回测任务列表/详情项（result 为绩效汇总，含 warnings）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    strategy_name: str
    start_date: str
    end_date: str
    initial_capital: float
    slippage_pct: float
    slippage_model: str = "fixed"  # fixed-固定百分比，amp-振幅比例
    commission_pct: float
    stamp_tax_pct: float
    status: str  # running-运行中，success-成功，failed-失败
    error_msg: Optional[str] = None
    result: Optional[dict] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class BacktestDetail(BacktestItem):
    """回测详情（额外含每日净值曲线）"""

    equity_curve: Optional[list] = None


class BacktestTradeItem(BaseModel):
    """回测成交明细项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    backtest_id: int
    stock_code: str
    stock_name: str
    action: str  # buy-买入，sell-卖出
    trade_date: str
    price: float
    quantity: int
    amount: float
    fee: float
    reason: Optional[str] = None
    return_rate: Optional[float] = None
    created_at: Optional[datetime] = None
