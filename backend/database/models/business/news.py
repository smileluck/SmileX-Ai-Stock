#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
新闻聚合表
存储多源聚合抓取的财经新闻
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, Integer, DateTime, UniqueConstraint, JSON
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class BusinessNews(Base):
    """
    新闻聚合表
    存储多源聚合抓取的财经新闻
    """

    __table_args__ = (
        UniqueConstraint("url", name="uk_news_url"),
        {"comment": "新闻聚合表"},
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="新闻标题")
    url: Mapped[str] = mapped_column(String(1000), nullable=False, comment="新闻原文链接")
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="新闻源 key")
    source_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="新闻源中文名")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="新闻正文", default=None)
    summary: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment="新闻摘要", default=None)
    author: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="作者", default=None)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="发布时间", default=None
    )
    raw_time: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="原始时间字符串", default=None)
    long_term_tags: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="长期事件标签（空=短期资讯；标签口径同轮动主题，采集时按关键词规则打标）",
    )


class BusinessNewsSyncLog(Base):
    """
    新闻采集日志表
    记录每次按源抓取的结果
    """

    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="新闻源 key")
    status: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="采集状态：True-成功，False-失败")
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="抓取条数", default=0)
    saved_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="入库条数", default=0)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息", default=None)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="开始时间", default=None
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="结束时间", default=None
    )
