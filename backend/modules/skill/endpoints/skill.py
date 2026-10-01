#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Skills 管理相关接口
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import t
from core.response.response_schema import ResponseModel, ResponsePageModel, response_base
from database.db_manager import get_session
from database.models.sys.user import SysUser
from modules.admin.deps.auth.permission import require_permission
from modules.admin.deps.auth.user_manager import current_user
from modules.common.schemas.page import PageRequest, get_page_params, get_paginated_results
from modules.skill.schemas.skill import (
    SkillCreate,
    SkillQueryParams,
    SkillResponseData,
    SkillStatusUpdate,
    SkillUpdate,
)
from modules.skill.services.skill_service import SkillService

logger = logging.getLogger(__name__)

skill_router = APIRouter(
    prefix="", tags=["环境配置/Skills管理"], dependencies=[Depends(current_user)]
)


@skill_router.get(
    "/list",
    response_model=ResponsePageModel[SkillResponseData],
    summary="技能列表（分页）",
    dependencies=[Depends(require_permission("skill:list"))],
)
async def get_skill_list(
    query_params: SkillQueryParams = Depends(),
    page_params: PageRequest = Depends(get_page_params),
    db: AsyncSession = Depends(get_session),
):
    """分页查询技能列表，支持名称/编码模糊搜索与状态筛选"""
    query = SkillService.build_query(query_params)
    page_data = await get_paginated_results(
        db=db,
        page_params=page_params,
        query=query,
        schema=SkillResponseData,
    )
    return response_base.page(data=page_data)


@skill_router.post(
    "/add",
    response_model=ResponseModel[SkillResponseData],
    summary="创建技能",
    dependencies=[Depends(require_permission("skill:manage"))],
)
async def create_skill(
    skill_in: SkillCreate,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    """创建技能，code 唯一"""
    skill = await SkillService.create_skill(db, skill_in)
    return response_base.success(
        data=SkillResponseData.model_validate(skill), msg=t("common.create_success")
    )


@skill_router.put(
    "/{skill_id}",
    response_model=ResponseModel[SkillResponseData],
    summary="更新技能（code 不可改）",
    dependencies=[Depends(require_permission("skill:manage"))],
)
async def update_skill(
    skill_id: int,
    skill_in: SkillUpdate,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    """更新技能信息，code 创建后不可修改"""
    skill = await SkillService.update_skill(db, skill_id, skill_in)
    return response_base.success(
        data=SkillResponseData.model_validate(skill), msg=t("common.update_success")
    )


@skill_router.put(
    "/{skill_id}/status",
    response_model=ResponseModel[SkillResponseData],
    summary="启用/禁用技能",
    dependencies=[Depends(require_permission("skill:manage"))],
)
async def update_skill_status(
    skill_id: int,
    body: SkillStatusUpdate,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    """启用/禁用技能，启用的技能在 Agent 对话时注入系统提示词"""
    skill = await SkillService.update_status(db, skill_id, body.status)
    return response_base.success(
        data=SkillResponseData.model_validate(skill), msg=t("common.status_update_success")
    )


@skill_router.delete(
    "/{skill_id}",
    response_model=ResponseModel,
    summary="删除技能",
    dependencies=[Depends(require_permission("skill:manage"))],
)
async def delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_session),
    user: SysUser = Depends(current_user),
):
    """删除技能"""
    await SkillService.delete_skill(db, skill_id)
    return response_base.success(msg=t("common.delete_success"))
