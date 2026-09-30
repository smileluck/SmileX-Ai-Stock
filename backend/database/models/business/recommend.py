#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 推荐股票表
- BusinessRecommendRun: 推荐执行记录（submit_run 落 running 即返，LLM 在后台任务中
  综合六维度候选池生成 10 只推荐股，结果为 markdown 综合研判 + 结构化推荐列表）
- BusinessRecommendStock: 单只推荐股（涨停候选/抄底两类，含预判买点/目标价/止损价，
  并回写关联的策略买入信号 ID，交易引擎据此自动建仓追踪）
"""

from datetime import date
from typing import Optional

from sqlalchemy import (
    String, Text, BigInteger, SmallInteger, Numeric, JSON, Date, ForeignKey, Index,
)
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class BusinessRecommendRun(Base):
    """AI 推荐执行记录表"""

    __table_args__ = (
        Index("ix_recommend_run_date", "run_date"),
        {"comment": "AI 推荐执行记录表"},
    )

    run_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="推荐日期（本地时区）"
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="schedule",
        comment="触发方式：schedule-定时，manual-手动",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running",
        comment="执行状态：running-执行中，success-成功，failed-失败",
    )
    error_msg: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="错误信息"
    )
    ai_raw_response: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="AI 原始回复文本（json 块 + markdown 综合研判）"
    )
    parsed_result: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="解析后的结构化推荐结果：{\"stocks\": [...]}",
    )
    candidate_snapshot: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="候选池摘要：六维度候选股及其量化线索（连板概率/热榜排名/板块资金/大宗上榜/超跌因子/相关资讯）",
    )
    strategy_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None,
        comment="关联的专用策略 ID（AI每日推荐，信号落库到该策略下）",
    )


class BusinessRecommendStock(Base):
    """AI 推荐个股表"""

    __table_args__ = (
        Index("ix_recommend_stock_run", "run_id"),
        {"comment": "AI 推荐个股表"},
    )

    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("business_recommend_run.id"),
        nullable=False, comment="推荐执行记录 ID",
    )
    rank: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="推荐排序（按评分降序 1-10）"
    )
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="证券代码")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="证券简称")
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="推荐方向：limit_up-涨停候选，bottom_fish-抄底",
    )
    score: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, comment="综合评分 0-100"
    )
    buy_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="预判买点（参考买价）"
    )
    target_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="目标价（预估卖点）"
    )
    stop_loss_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, default=None, comment="止损价"
    )
    entry_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="market",
        comment="建仓方式：market-按实时价直接成交，limit-触及买点（实时价<=买点）才成交",
    )
    reasons: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="六维度小结论：{news,sentiment,factor,sector_fund,main_force,limit_up}",
    )
    summary: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="一句话推荐逻辑"
    )
    signal_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None,
        comment="关联的策略买入信号 ID（business_strategy_signal.id）",
    )
