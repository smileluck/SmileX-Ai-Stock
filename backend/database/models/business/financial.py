#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
企业财报表
- BusinessFinancialReport: 个股财报关键指标快照（按「股票×报告期」唯一 upsert）
- BusinessFinancialInterpretation: AI 财报解读执行记录
  （submit 落库即返、后台 LLM 生成，三态 status，与 BusinessAnalysisRun 同模式）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, JSON, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class BusinessFinancialReport(Base):
    """企业财报关键指标表"""

    __table_args__ = (
        UniqueConstraint("stock_code", "report_period", name="uk_fin_report_code_period"),
        Index("ix_fin_report_code", "stock_code"),
        {"comment": "企业财报关键指标表"},
    )

    stock_code: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="股票代码（6 位）",
    )
    report_period: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="报告期 YYYY-MM-DD（如 2026-06-30）",
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="抓取时间",
    )
    stock_name: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None, comment="股票名称",
    )
    metrics: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="财报关键指标（营收/净利/同比/ROE/毛利率等，列名→值）",
    )


class BusinessFinancialInterpretation(Base):
    """AI 财报解读执行记录表"""

    __table_args__ = (
        Index("ix_fin_interp_code_created", "stock_code", "created_at"),
        {"comment": "AI 财报解读执行记录表"},
    )

    stock_code: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="股票代码（6 位）",
    )
    run_date: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="执行日期 YYYY-MM-DD（定时任务同日去重用）",
    )
    stock_name: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None, comment="股票名称",
    )
    report_period: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, default=None, comment="解读所基于的报告期 YYYY-MM-DD",
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="schedule",
        comment="触发方式：schedule-定时（持仓自动），manual-手动",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running",
        comment="执行状态：running-执行中，success-成功，failed-失败",
    )
    ai_raw_response: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="AI 财报解读报告原文（markdown）",
    )
    parsed_result: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="结构化摘要：{quality_rating, highlights, risks, forecast}",
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default=None,
        comment="所属行业（研报表/东财个股信息）",
    )
    error_msg: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None, comment="错误信息",
    )


class BusinessFinancialConfig(Base):
    """财报 AI 解读分析策略配置表（单行，prompt 为空则使用内置默认策略）"""

    __table_args__ = (
        {"comment": "财报 AI 解读分析策略配置表"},
    )

    prompt_template: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None,
        comment="分析策略定制提示词（关注面/风格/风控偏好等，空则使用默认策略）",
    )
