#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""AI 技能包表：存储 Agent 技能指令，启用的技能在 Agent 对话时注入系统提示词。"""

from typing import Optional

from sqlalchemy import String, Boolean, Integer, Text
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class SysSkill(Base):
    """
    AI 技能包表
    存储 Agent 技能（名称 + 编码 + 指令内容），启用的技能按 sort 排序
    在 Agent 对话时拼入系统提示词，指导 LLM 按技能指令行事
    """

    # 技能名称
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="技能名称")
    # 技能编码（唯一，小写字母/数字/下划线）
    code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False, comment="技能编码"
    )
    # 技能指令内容（提示词正文）
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="技能指令内容")
    # 技能描述
    description: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None, comment="技能描述"
    )
    # 状态（True-启用，False-禁用）
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="状态：True-启用，False-禁用")
    # 排序（注入提示词的优先级，越小越靠前）
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序（越小越靠前）")
