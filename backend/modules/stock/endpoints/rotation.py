#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
板块轮动分析接口
"""
import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, response_base
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.stock.services.rotation_service import RotationService
from modules.stock.schemas.rotation import (
    RotationOverviewResponse,
    RotationSwitchResponse,
    RotationSyncResult,
    RotationBackfillResult,
)

logger = logging.getLogger(__name__)

rotation_router = APIRouter(prefix="/rotation", tags=["A股/板块轮动"])


@rotation_router.get(
    "/overview",
    response_model=ResponseModel[RotationOverviewResponse],
    summary="获取近期轮动板块总览",
    dependencies=[Depends(require_permission("stock:board:list"))],
)
async def get_rotation_overview(
    board_type: Literal["industry", "concept"] = Query("industry", description="板块类型: industry/concept"),
    days: int = Query(10, ge=5, le=60, description="回看交易日数"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """近期轮动板块指标（读时计算）：阶段/明日候选评分/操作建议/量比/资金/涨停梯队"""
    data = await RotationService.get_overview(db, board_type, days)
    return response_base.success(data=data)


@rotation_router.get(
    "/switch",
    response_model=ResponseModel[RotationSwitchResponse],
    summary="获取板块内高低切换信号",
    dependencies=[Depends(require_permission("stock:board:list"))],
)
async def get_rotation_switch(
    board_type: Literal["industry", "concept"] = Query("industry", description="板块类型: industry/concept"),
    top_n: int = Query(15, ge=5, le=30, description="当日涨幅榜前 N 板块"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """当日涨幅榜前 N 板块的成分股高低位分层与切换信号，附高位滞涨/低位启动个股名单"""
    data = await RotationService.get_switch_signals(db, board_type, top_n)
    return response_base.success(data=data)


@rotation_router.post(
    "/sync_stocks",
    response_model=ResponseModel[RotationSyncResult],
    summary="手动同步板块成分股快照",
    dependencies=[Depends(require_permission("stock:board:sync"))],
)
async def sync_rotation_stocks(
    concept_top: int = Query(30, ge=5, le=100, description="概念板块按当日涨幅取前 N"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """抓取活跃板块（行业全量 + 概念涨幅前 N）全部成分股写入当日快照"""
    result = await RotationService.sync_board_stocks(db, concept_top)
    return response_base.success(data=result, msg="板块成分股同步完成")


@rotation_router.post(
    "/backfill",
    response_model=ResponseModel[RotationBackfillResult],
    summary="提交板块历史日K回填（后台执行）",
    dependencies=[Depends(require_permission("stock:board:sync"))],
)
async def backfill_rotation_history(
    board_type: Literal["industry", "concept", "all"] = Query(
        "all", description="板块类型: industry/concept/all（all=行业+概念合并为一个后台任务）"),
    days: int = Query(60, ge=10, le=250, description="回填天数"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """通过东财板块日K回填 business_board_daily 历史缺失日期，立即返回后台执行"""
    result = await RotationService.submit_backfill(db, board_type, days)
    return response_base.success(data=result, msg="板块历史回填已提交后台执行")
