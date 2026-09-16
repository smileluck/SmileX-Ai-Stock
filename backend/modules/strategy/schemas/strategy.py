#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 分析策略相关 Schema
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

# 执行时段常量（策略配置与执行记录共用）
EXECUTE_PERIODS = ("pre_market", "morning", "noon", "tail", "post_close")

EXECUTE_PERIOD_NAMES = {
    "pre_market": "早盘集合竞价",
    "morning": "早盘",
    "noon": "午盘",
    "tail": "尾盘",
    "post_close": "盘后",
    "manual": "手动执行",
    "review": "盘中持仓复核（涨停保护触发）",
}

# 策略分类常量（预置策略与用户自建共用，自建默认 general）
STRATEGY_CATEGORIES = ("pre_market_auction", "noon", "tail", "blue_chip", "general")

STRATEGY_CATEGORY_NAMES = {
    "pre_market_auction": "早盘竞价",
    "noon": "午盘",
    "tail": "尾盘",
    "blue_chip": "蓝筹白马",
    "general": "综合",
}

# 策略类型常量：prompt-LLM 提示词策略，rule-规则型策略（因子条件固化）
STRATEGY_TYPES = ("prompt", "rule")

# 规则条件操作符（不支持 top_n——策略信号是逐股布尔判定，非截面排名选股）
RULE_OPS = ("gt", "gte", "lt", "lte")


class RuleCondition(BaseModel):
    """单条规则条件：因子值与阈值的比较"""

    factor_id: int = Field(..., description="因子 ID")
    op: Literal["gt", "gte", "lt", "lte"] = Field(..., description="比较操作符")
    value: float = Field(..., description="阈值")


class RuleConfig(BaseModel):
    """规则型策略配置：买入/卖出条件各自组内 AND；sell_conditions 为空表示
    不做规则卖出（仅依赖止损/止盈/回撤等机械离场）"""

    buy_conditions: list[RuleCondition] = Field(..., min_length=1, max_length=10, description="买入条件（AND）")
    sell_conditions: list[RuleCondition] = Field(default_factory=list, max_length=10, description="卖出条件（AND），可为空")


class StrategyCreateRequest(BaseModel):
    """创建策略请求"""

    name: str = Field(..., min_length=1, max_length=100, description="策略名称")
    description: Optional[str] = Field(None, max_length=500, description="策略描述")
    category: str = Field("general", max_length=30, description="策略分类")
    prompt_template: Optional[str] = Field(None, description="策略定制提示词")
    stock_pool: Optional[dict] = Field(None, description="股票池 {codes: [...]}")
    execute_periods: list[str] = Field(
        default_factory=lambda: ["morning"], description="执行时段列表"
    )
    max_positions: int = Field(10, ge=1, le=100, description="最大同时持仓数")
    stop_loss_pct: Optional[float] = Field(5.0, ge=0, le=100, description="默认止损比例(%)")
    take_profit_pct: Optional[float] = Field(10.0, ge=0, le=500, description="默认止盈比例(%)")
    trailing_drawdown_pct: Optional[float] = Field(
        5.0, ge=0, le=100,
        description="回撤止盈比例(%)：现价自持仓期间最高价回撤超该值且仍浮盈时止盈离场，0或不填不启用",
    )
    status: bool = Field(True, description="状态：True-启用，False-停用")
    strategy_type: Literal["prompt", "rule"] = Field(
        "prompt", description="策略类型：prompt-LLM 提示词策略，rule-规则型策略；创建后不可改（更新时忽略）"
    )
    rule_config: Optional[RuleConfig] = Field(
        None, description="规则型策略配置（rule 型必填且 buy_conditions 非空；prompt 型必须为 null）"
    )


class StrategyUpdateRequest(StrategyCreateRequest):
    """更新策略请求（全量字段）"""

    pass


class StrategyItem(BaseModel):
    """策略列表项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    category: str = "general"
    is_preset: bool = False
    is_template: bool = False
    source_id: Optional[int] = None
    tags: Optional[list[str]] = None
    prompt_template: Optional[str] = None
    stock_pool: Optional[dict] = None
    execute_periods: Optional[list] = None
    max_positions: int
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_drawdown_pct: Optional[float] = None
    status: bool
    strategy_type: str = "prompt"
    rule_config: Optional[RuleConfig] = None
    last_executed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ----------------------------------------------------------------------
# 策略模板市场（克隆 / 发布 / 导出 / 导入）
# ----------------------------------------------------------------------

# 导出 JSON 的 schema 版本（仅接受 1，便于将来兼容演进）
STRATEGY_EXPORT_SCHEMA_VERSION = 1


class TemplatePublishRequest(BaseModel):
    """发布/下架模板请求（body 可选，tags 传入时覆盖更新）"""

    tags: Optional[list[str]] = Field(None, max_length=10, description="模板标签，如 [\"打板\", \"短线\"]")


class TemplateBacktestSummary(BaseModel):
    """最近一次 success 回测的绩效摘要（无则整体为 null）"""

    start_date: str
    end_date: str
    total_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: Optional[int] = None


class TemplateItem(StrategyItem):
    """模板市场列表项：策略详情 + 克隆次数 + 最近回测摘要"""

    clone_count: int = 0
    last_backtest: Optional[TemplateBacktestSummary] = None


class StrategyExportData(BaseModel):
    """策略可移植导出 JSON（不含 id/状态/时间戳）"""

    schema_version: int = STRATEGY_EXPORT_SCHEMA_VERSION
    name: str
    description: Optional[str] = None
    category: str = "general"
    prompt_template: Optional[str] = None
    stock_pool: Optional[dict] = None
    execute_periods: Optional[list[str]] = None
    max_positions: int = 10
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_drawdown_pct: Optional[float] = None
    tags: Optional[list[str]] = None
    strategy_type: str = "prompt"
    rule_config: Optional[RuleConfig] = None


class StrategyImportRequest(BaseModel):
    """导入策略请求（字段口径同创建接口；schema_version 仅接受 1）"""

    schema_version: int = Field(..., description="导出 JSON 的 schema 版本，当前仅支持 1")
    name: str = Field(..., min_length=1, max_length=100, description="策略名称（冲突时自动追加序号）")
    description: Optional[str] = Field(None, max_length=500, description="策略描述")
    category: str = Field("general", max_length=30, description="策略分类")
    prompt_template: Optional[str] = Field(None, description="策略定制提示词")
    stock_pool: Optional[dict] = Field(None, description="股票池 {codes: [...]}")
    execute_periods: list[str] = Field(
        default_factory=lambda: ["morning"], description="执行时段列表"
    )
    max_positions: int = Field(10, ge=1, le=100, description="最大同时持仓数")
    stop_loss_pct: Optional[float] = Field(5.0, ge=0, le=100, description="默认止损比例(%)")
    take_profit_pct: Optional[float] = Field(10.0, ge=0, le=500, description="默认止盈比例(%)")
    trailing_drawdown_pct: Optional[float] = Field(
        5.0, ge=0, le=100, description="回撤止盈比例(%)，0或不填不启用"
    )
    tags: Optional[list[str]] = Field(None, max_length=10, description="策略标签")
    strategy_type: Literal["prompt", "rule"] = Field(
        "prompt", description="策略类型（旧格式导出 JSON 无此字段，缺省 prompt）"
    )
    rule_config: Optional[RuleConfig] = Field(
        None, description="规则型策略配置（rule 型必填；prompt 型必须为 null）"
    )


class StrategyRunItem(BaseModel):
    """策略执行记录项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    strategy_name: str
    run_period: str
    run_date: str
    trigger_type: str
    status: str  # running-执行中，success-成功，failed-失败
    parsed_signals: Optional[list] = None
    opened_count: int
    closed_count: int
    error_msg: Optional[str] = None
    created_at: Optional[datetime] = None


class SignalItem(BaseModel):
    """单条 AI 信号（LLM 结构化输出）"""

    stock_code: str
    stock_name: str = ""
    action: str  # buy / sell / hold / adjust
    buy_price: Optional[float] = None
    target_sell_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    reason: Optional[str] = None


class StrategyRunSubmitResult(BaseModel):
    """策略执行提交结果（异步执行：接口立即返回，结果见执行记录）"""

    run_id: int
    status: str = "running"


class PositionItem(BaseModel):
    """持仓项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    strategy_name: str
    stock_code: str
    stock_name: str
    buy_price: float
    buy_time: datetime
    buy_reason: Optional[str] = None
    quantity: int
    target_sell_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    trailing_drawdown_pct: Optional[float] = None
    peak_price: Optional[float] = None
    status: str
    latest_price: Optional[float] = None
    floating_pnl_pct: Optional[float] = None
    tracked_at: Optional[datetime] = None
    sell_price: Optional[float] = None
    sell_time: Optional[datetime] = None
    sell_reason: Optional[str] = None
    return_rate: Optional[float] = None


class PositionCloseRequest(BaseModel):
    """手动平仓请求"""

    price: Optional[float] = Field(None, gt=0, description="卖出价，为空取最新价")
    reason: Optional[str] = Field(None, max_length=500, description="卖出备注")


class TrackLogItem(BaseModel):
    """持仓跟踪日志项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    position_id: int
    track_time: datetime
    latest_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    ai_adjusted_target: Optional[float] = None
    adjust_reason: Optional[str] = None


class StrategyStatsItem(BaseModel):
    """策略回报率统计"""

    strategy_id: int
    strategy_name: str
    holding_count: int = 0
    closed_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: Optional[float] = None  # 胜率(%)，无平仓记录时为空
    total_return_rate: Optional[float] = None  # 累计收益率(%)，各笔等权简单加总
    avg_return_rate: Optional[float] = None  # 平均单笔收益率(%)
    best_return_rate: Optional[float] = None
    worst_return_rate: Optional[float] = None
