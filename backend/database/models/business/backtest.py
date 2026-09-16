#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略回测表
回放已记录的真实 AI 信号（business_strategy_signal），按历史日线逐日模拟撮合，
不做 LLM 逐日重放（行情/资讯快照是当前值，逐日重放存在前视偏差）。
- BusinessBacktest: 回测任务（参数快照 + 状态 + 绩效汇总 + 净值曲线）
- BusinessBacktestTrade: 回测成交明细（逐笔买卖记录）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, BigInteger, Numeric, Text, DateTime, JSON, Index
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class BusinessBacktest(Base):
    """策略回测任务表"""

    __table_args__ = (
        Index("ix_backtest_strategy_created", "strategy_id", "created_at"),
        {"comment": "策略回测任务表"},
    )

    strategy_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="策略 ID"
    )
    strategy_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="策略名称（回测发起时快照）"
    )
    start_date: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="回测开始日期 YYYY-MM-DD"
    )
    end_date: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="回测结束日期 YYYY-MM-DD"
    )
    initial_capital: Mapped[float] = mapped_column(
        Numeric(16, 2), nullable=False, comment="初始资金（元）"
    )
    slippage_pct: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, default=0.1, comment="滑点比例(%)，买卖双边"
    )
    commission_pct: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, default=0.025,
        comment="佣金比例(%)，万2.5=0.025，最低 5 元",
    )
    stamp_tax_pct: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, default=0.05,
        comment="印花税比例(%)，仅卖出收取",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running",
        comment="回测状态：running-运行中，success-成功，failed-失败",
    )
    error_msg: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="失败原因"
    )
    result: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="绩效汇总：total_return_pct/annual_return_pct/max_drawdown_pct/sharpe/"
                "win_count/loss_count/win_rate/profit_factor/trade_count/final_equity/warnings",
    )
    equity_curve: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="每日净值曲线：[{date, equity, cash, market_value}, ...]",
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="开始执行时间"
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="执行完成时间"
    )


class BusinessBacktestTrade(Base):
    """策略回测成交明细表"""

    __table_args__ = (
        Index("ix_backtest_trade_backtest", "backtest_id"),
        {"comment": "策略回测成交明细表"},
    )

    backtest_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="回测任务 ID"
    )
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="证券代码")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="证券简称")
    action: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="成交动作：buy-买入，sell-卖出"
    )
    trade_date: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="成交日期 YYYY-MM-DD"
    )
    price: Mapped[float] = mapped_column(
        Numeric(16, 4), nullable=False, comment="成交价（含滑点）"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="成交数量（股，100 的整数倍）"
    )
    amount: Mapped[float] = mapped_column(
        Numeric(16, 2), nullable=False, comment="成交金额（元）"
    )
    fee: Mapped[float] = mapped_column(
        Numeric(16, 2), nullable=False, comment="交易费用（佣金+印花税，元）"
    )
    reason: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None,
        comment="买入理由（AI 信号原文）或卖出原因：stop_loss/target_reached/trailing_stop/"
                "ai_signal/backtest_end",
    )
    return_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, default=None,
        comment="该笔收益率(%)，仅 sell 记录（相对买入成交价，不含费用）",
    )
