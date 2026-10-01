#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Skills 管理 Service"""

import logging

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from core.exception.errors import ConflictError, NotFoundError
from core.i18n import t
from database.models.sys.skill import SysSkill
from modules.skill.schemas.skill import SkillCreate, SkillQueryParams, SkillUpdate

logger = logging.getLogger(__name__)


class SkillService:
    """Skills 管理"""

    @staticmethod
    def build_query(query_params: SkillQueryParams) -> Select:
        """构建分页查询"""
        base_query = select(SysSkill)
        conditions = []
        if query_params.name:
            conditions.append(SysSkill.name.contains(query_params.name))
        if query_params.code:
            conditions.append(SysSkill.code.contains(query_params.code))
        if query_params.status is not None:
            conditions.append(SysSkill.status == query_params.status)
        if conditions:
            base_query = base_query.where(and_(*conditions))
        return base_query.order_by(SysSkill.sort.asc(), SysSkill.id.desc())

    @staticmethod
    async def get_skill(db: AsyncSession, skill_id: int) -> SysSkill:
        """获取单个技能"""
        result = await db.execute(select(SysSkill).where(SysSkill.id == skill_id))
        skill = result.scalar_one_or_none()
        if not skill:
            raise NotFoundError(msg=t("skill.not_found", id=skill_id))
        return skill

    @staticmethod
    async def create_skill(db: AsyncSession, skill_in: SkillCreate) -> SysSkill:
        """创建技能"""
        result = await db.execute(
            select(SysSkill).where(SysSkill.code == skill_in.code)
        )
        if result.scalar_one_or_none():
            raise ConflictError(msg=t("skill.code_exist"))

        skill = SysSkill(
            code=skill_in.code,
            name=skill_in.name,
            content=skill_in.content,
            description=skill_in.description,
            status=skill_in.status,
            sort=skill_in.sort,
        )
        db.add(skill)
        await db.commit()
        await db.refresh(skill)
        logger.info("创建技能成功，ID: %d，编码: %s", skill.id, skill.code)
        return skill

    @staticmethod
    async def update_skill(
        db: AsyncSession, skill_id: int, skill_in: SkillUpdate
    ) -> SysSkill:
        """更新技能（code 不可改）"""
        skill = await SkillService.get_skill(db, skill_id)

        update_data = skill_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(skill, field, value)

        await db.commit()
        await db.refresh(skill)
        logger.info("更新技能成功，ID: %d", skill_id)
        return skill

    @staticmethod
    async def update_status(db: AsyncSession, skill_id: int, status: bool) -> SysSkill:
        """启用/禁用技能"""
        skill = await SkillService.get_skill(db, skill_id)
        skill.status = status
        await db.commit()
        await db.refresh(skill)
        logger.info("更新技能状态成功，ID: %d，status: %s", skill_id, status)
        return skill

    @staticmethod
    async def delete_skill(db: AsyncSession, skill_id: int) -> bool:
        """删除技能"""
        skill = await SkillService.get_skill(db, skill_id)
        await db.delete(skill)
        await db.commit()
        logger.info("删除技能成功，ID: %d", skill_id)
        return True

    @staticmethod
    async def list_enabled(db: AsyncSession) -> list[SysSkill]:
        """获取所有启用的技能（Agent 系统提示词注入用，按 sort 升序）"""
        result = await db.execute(
            select(SysSkill)
            .where(SysSkill.status == True)  # noqa: E712
            .order_by(SysSkill.sort.asc(), SysSkill.id.asc())
        )
        return list(result.scalars().all())
