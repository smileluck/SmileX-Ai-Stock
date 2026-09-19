#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 分析策略表
支持定制策略（提示词 + 股票池 + 执行时段），LLM 生成买卖点，
模拟盘跟踪持仓并计算回报率
- BusinessAiStrategy: 策略配置
- BusinessStrategyRun: 策略执行记录（AI 原始输出 + 解析后的信号）
- BusinessStrategySignal: 待执行买卖信号（LLM 分析产出，由每分钟交易引擎按实时价执行）
- BusinessStrategyPosition: 个股模拟持仓（买点/预估卖点/跟踪/回报率）
- BusinessPositionTrackLog: 持仓跟踪日志（每次跟踪的价格与浮盈快照）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, BigInteger, Numeric, Boolean, Text, DateTime, JSON, Index,
    UniqueConstraint, Computed,
)
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class BusinessAiStrategy(Base):
    """AI 分析策略配置表"""

    __table_args__ = (
        Index("ix_ai_strategy_status", "status"),
        Index("ix_ai_strategy_is_template", "is_template"),
        Index("ix_ai_strategy_source_id", "source_id"),
        Index("ix_ai_strategy_strategy_type", "strategy_type"),
        {"comment": "AI 分析策略配置表"},
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="策略名称")
    description: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="策略描述"
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="general", index=True,
        comment="策略分类：pre_market_auction/noon/tail/blue_chip/general",
    )
    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否系统预置策略"
    )
    prompt_template: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="策略定制提示词（选股逻辑、风控要求等）"
    )
    stock_pool: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="股票池：{\"codes\": [\"600519\", ...]}，为空则由 AI 在全市场内自主选择",
    )
    execute_periods: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="执行时段列表：pre_market/morning/noon/tail/post_close",
    )
    max_positions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, comment="最大同时持仓数"
    )
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, default=5.0, comment="默认止损比例(%)，相对买价"
    )
    take_profit_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, default=10.0, comment="默认止盈比例(%)，相对买价"
    )
    trailing_drawdown_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, default=5.0,
        comment="回撤止盈比例(%)：现价自持仓期间最高价回撤超该值且仍浮盈时止盈离场",
    )
    status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="状态：True-启用，False-停用"
    )
    last_executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="最近执行时间"
    )
    is_template: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否已发布为模板（模板市场可见）"
    )
    source_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None, comment="克隆/导入来源策略 ID"
    )
    tags: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=None, comment="标签列表，如 [\"打板\", \"短线\"]"
    )
    strategy_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="prompt",
        comment="策略类型：prompt-LLM 提示词策略，rule-规则型策略（因子条件固化）；创建后不可改",
    )
    rule_config: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment='规则型策略配置：{"buy_conditions": [{factor_id, op, value}], '
                '"sell_conditions": [...]}，op ∈ gt/gte/lt/lte；prompt 型必须为 NULL',
    )


class BusinessStrategyRun(Base):
    """策略执行记录表"""

    __table_args__ = (
        Index("ix_strategy_run_strategy", "strategy_id", "created_at"),
        # 生成列模拟部分唯一索引：仅 running 记录占用 strategy_id 键位，
        # MySQL 唯一索引允许多个 NULL，非 running 不受限（防并发重复 running）
        UniqueConstraint("running_key", name="uq_strategy_run_running"),
        {"comment": "策略执行记录表"},
    )

    strategy_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="策略 ID"
    )
    strategy_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="策略名称（执行时快照）"
    )
    run_period: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="执行时段：pre_market/morning/noon/tail/post_close/manual"
    )
    run_date: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="执行日期 YYYY-MM-DD（同日同时段去重用）"
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="schedule",
        comment="触发方式：schedule-定时，manual-手动"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running",
        comment="执行状态：running-执行中，success-成功，failed-失败",
    )
    ai_raw_response: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="AI 原始回复文本"
    )
    parsed_signals: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=None, comment="解析后的结构化信号列表"
    )
    opened_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="新建仓数量（交易引擎执行信号时累加）"
    )
    closed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="平仓数量（交易引擎执行信号时累加）"
    )
    error_msg: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="错误信息"
    )
    running_key: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        Computed("CASE WHEN status='running' THEN strategy_id ELSE NULL END"),
        nullable=True,
        default=None,
        comment="运行唯一键（生成列）：status=running 时为 strategy_id，否则 NULL，"
                "配合 uq_strategy_run_running 保证同策略仅一条 running",
    )


class BusinessStrategySignal(Base):
    """策略待执行买卖信号表（LLM 分析产出，交易引擎每分钟按实时价执行模拟买卖）"""

    __table_args__ = (
        Index("ix_strategy_signal_strategy_status", "strategy_id", "status"),
        Index("ix_strategy_signal_run", "run_id"),
        Index("ix_strategy_signal_stock", "stock_code"),
        {"comment": "策略待执行买卖信号表"},
    )

    strategy_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="策略 ID"
    )
    strategy_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="策略名称（信号产生时快照）"
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="来源执行记录 ID"
    )
    run_period: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="执行时段：pre_market/morning/noon/tail/post_close/manual"
    )
    run_date: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="信号产生日期 YYYY-MM-DD（过期判断用）"
    )
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="证券代码")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="证券简称")
    action: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="信号动作：buy-买入，sell-卖出平仓，adjust-调整卖点/止损"
    )
    ref_buy_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="AI 参考买价"
    )
    target_sell_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="预估卖点（目标价）"
    )
    stop_loss_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="止损价"
    )
    reason: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="AI 给出的信号理由"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True,
        comment="信号状态：pending-待执行，executed-已执行，skipped-已跳过，failed-执行失败，expired-已过期",
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="执行时间"
    )
    executed_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="实际成交价"
    )
    result_msg: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="执行结果说明（跳过/失败原因）"
    )


class BusinessStrategyPosition(Base):
    """策略个股模拟持仓表"""

    __table_args__ = (
        Index("ix_strategy_position_strategy_status", "strategy_id", "status"),
        Index("ix_strategy_position_stock", "stock_code"),
        Index("ix_strategy_position_run", "run_id"),
        {"comment": "策略个股模拟持仓表"},
    )

    strategy_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="策略 ID"
    )
    strategy_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="策略名称（建仓时快照）"
    )
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="证券代码")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="证券简称")

    buy_price: Mapped[float] = mapped_column(
        Numeric(16, 4), nullable=False, comment="买入价（信号触发时最新价）"
    )
    buy_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="买入时间"
    )
    buy_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="AI 给出的买入理由"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, comment="持仓数量（股，默认一手）"
    )

    target_sell_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="预估卖点（目标价）"
    )
    stop_loss_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="止损价"
    )
    trailing_drawdown_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, default=None,
        comment="建仓时快照的策略回撤止盈比例(%)，空则不启用",
    )
    peak_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="持仓期间最高价（回撤止盈基准）"
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="holding",
        comment="持仓状态：holding-持仓中，closed-已平仓，cancelled-已取消",
    )

    latest_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="最新价（跟踪任务刷新）"
    )
    floating_pnl_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, default=None, comment="浮动盈亏比例(%)"
    )
    tracked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="最近跟踪时间"
    )

    sell_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="卖出价"
    )
    sell_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="卖出时间"
    )
    sell_reason: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None,
        comment="卖出原因：stop_loss/target_reached/trailing_stop/ai_signal/manual",
    )
    return_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, default=None, comment="最终收益率(%)，平仓时计算"
    )
    run_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None,
        comment="建仓来源执行记录 ID（2026-09-16 起写入，存量为 NULL）",
    )


class BusinessPositionTrackLog(Base):
    """持仓跟踪日志表"""

    __table_args__ = (
        Index("ix_position_track_position", "position_id", "track_time"),
        {"comment": "持仓跟踪日志表"},
    )

    position_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="持仓 ID"
    )
    track_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="跟踪时间"
    )
    latest_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="当时最新价"
    )
    pnl_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, default=None, comment="当时浮动盈亏(%)"
    )
    ai_adjusted_target: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="AI 本次调整后的预估卖点"
    )
    adjust_reason: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="调整理由（未调整为空）"
    )
