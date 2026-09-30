#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class SysDataSourceStat(Base):
    """数据源用量小时聚合统计表（core.datasource.stats 定时刷盘）"""

    __table_args__ = (
        UniqueConstraint("source_key", "stat_hour", name="uq_data_source_stat_hour"),
        {"comment": "数据源用量小时聚合统计表"},
    )

    source_key: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True, comment="数据源标识（core.datasource.registry）"
    )
    stat_hour: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="统计小时桶（整点）"
    )
    total_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="总调用次数"
    )
    success_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="成功次数"
    )
    fail_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="失败次数"
    )
    timeout_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="超时次数"
    )
    rejected_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="被禁用/熔断拒绝次数"
    )
    total_latency_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="总耗时（毫秒，求平均用）"
    )
    max_latency_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="单次最大耗时（毫秒）"
    )
