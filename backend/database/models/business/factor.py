#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
因子管理表
因子来源两条腿：预置开源公式因子库（WorldQuant Alpha101 / 经典价量因子，
随迁移种子入库，source=preset）与在线导入/自建（source=imported/custom）。
公式为 DSL 文本（modules/factor/services/formula.py 安全求值，严禁 eval/exec），
保存时即做解析校验，非法公式拒绝入库。
"""

from typing import Optional

from sqlalchemy import String, Boolean, Text, JSON, Index
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class BusinessFactor(Base):
    """因子库表"""

    __table_args__ = (
        Index("ix_factor_category", "category"),
        Index("ix_factor_source", "source"),
        {"comment": "因子库表"},
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="因子名称")
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="因子编码（唯一），如 alpha101_006/bias20"
    )
    formula: Mapped[str] = mapped_column(
        Text, nullable=False, comment="因子公式（DSL，安全求值器解析）"
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="custom",
        comment="因子分类：momentum-动量，volume-量价，price-价格，volatility-波动，custom-自定义",
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="因子描述"
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom",
        comment="来源：preset-预置开源因子库，imported-在线导入，custom-手工自建",
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="来源链接（论文/研报/开源仓库）"
    )
    params: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=None, comment="预留参数化配置（JSON，暂不使用）"
    )
    status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="状态：True-启用，False-停用"
    )
