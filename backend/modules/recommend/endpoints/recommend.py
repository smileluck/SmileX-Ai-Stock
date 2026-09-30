#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 推荐股票相关接口
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, ResponsePageDataModel, response_base
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.recommend.schemas.recommend import (
    RecommendRunDetailItem,
    RecommendRunItem,
    RecommendRunSubmitResult,
    RecommendStockItem,
)
from modules.recommend.services.recommend_service import RecommendService

logger = logging.getLogger(__name__)

recommend_router = APIRouter(prefix="", tags=["AI助手/推荐股票"])


def _page_data(records, page, page_size, total):
    return ResponsePageDataModel(
        records=records, page=page, page_size=page_size, total=total,
        total_pages=(total + page_size - 1) // page_size if page_size else 0,
    )


def _to_detail(run, stocks) -> RecommendRunDetailItem:
    detail = RecommendRunDetailItem.model_validate(run)
    detail.stocks = [RecommendStockItem.model_validate(s) for s in stocks]
    return detail


# ----------------------------------------------------------------------
# 生成推荐
# ----------------------------------------------------------------------
@recommend_router.post(
    "/run",
    response_model=ResponseModel[RecommendRunSubmitResult],
    summary="手动触发生成 AI 推荐股票（异步，立即返回）",
    dependencies=[Depends(require_permission("recommend:run"))],
)
async def run_recommend(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """手动生成推荐：创建执行记录后立即返回，候选收集与 LLM 生成在后台进行，
    前端轮询 latest 或 runs 接口查看进度与结果；当天已有生成中的记录时拒绝"""
    run_id = await RecommendService.submit_run(db, trigger_type="manual")
    return response_base.success(
        data=RecommendRunSubmitResult(run_id=run_id),
        msg="已提交生成，请稍后查看推荐结果",
    )


# ----------------------------------------------------------------------
# 查询
# ----------------------------------------------------------------------
@recommend_router.get(
    "/latest",
    response_model=ResponseModel[RecommendRunDetailItem | None],
    summary="获取最新一次推荐（含 10 只推荐股与 AI 研判原文，无记录时 data 为空）",
    dependencies=[Depends(require_permission("recommend:list"))],
)
async def get_latest_recommend(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await RecommendService.get_latest(db)
    if result is None:
        return response_base.success(data=None)
    run, stocks = result
    return response_base.success(data=_to_detail(run, stocks))


@recommend_router.get(
    "/runs",
    response_model=ResponseModel[ResponsePageDataModel[RecommendRunItem]],
    summary="分页获取推荐历史记录",
    dependencies=[Depends(require_permission("recommend:list"))],
)
async def get_recommend_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    runs, total = await RecommendService.get_runs(db, page, page_size)
    items = [RecommendRunItem.model_validate(row) for row in runs]
    return response_base.success(data=_page_data(items, page, page_size, total))


@recommend_router.get(
    "/runs/{run_id}",
    response_model=ResponseModel[RecommendRunDetailItem],
    summary="获取推荐记录详情（含推荐股列表与 AI 研判原文）",
    dependencies=[Depends(require_permission("recommend:list"))],
)
async def get_recommend_run_detail(
    run_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    run, stocks = await RecommendService.get_run_detail(db, run_id)
    return response_base.success(data=_to_detail(run, stocks))
