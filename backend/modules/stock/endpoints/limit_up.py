#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
涨停/炸板股池（热门个股）接口
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, ResponsePageDataModel, response_base
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.common.schemas.page import PageRequest, get_page_params
from modules.stock.services.limit_up_service import LimitUpService
from modules.stock.schemas.limit_up import LimitUpStockItem, LimitUpStats

logger = logging.getLogger(__name__)

limit_up_router = APIRouter(prefix="/limit-up", tags=["A股/热门个股"])


@limit_up_router.post(
    "/sync",
    response_model=ResponseModel[dict],
    summary="手动触发涨停/炸板股池同步",
    dependencies=[Depends(require_permission("stock:limit_up:sync"))],
)
async def sync_limit_up(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """手动抓取当日涨停股池与炸板股池并写入快照"""
    result = await LimitUpService.sync_all(db)
    return response_base.success(data=result, msg="涨停/炸板股池同步完成")


@limit_up_router.get(
    "/list",
    response_model=ResponseModel,
    summary="获取涨停/炸板股列表（分页）",
    dependencies=[Depends(require_permission("stock:limit_up:list"))],
)
async def get_limit_up_list(
    date: str | None = Query(None, description="快照日期 YYYY-MM-DD，为空取最新"),
    market_board: str = Query(
        "all", description="市场板块: all/main/chinext/star"
    ),
    pool_type: str = Query(
        "all", description="池类型: all/limit_up/broken（broken=涨停后炸板未封住）"
    ),
    page_params: PageRequest = Depends(get_page_params),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """获取涨停/炸板股列表，支持按市场板块与池类型筛选"""
    offset = (page_params.page - 1) * page_params.page_size
    items, total = await LimitUpService.get_list(
        db, date, market_board, pool_type, offset, page_params.page_size
    )
    total_pages = (total + page_params.page_size - 1) // page_params.page_size
    page_data = ResponsePageDataModel(
        records=items,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
        total_pages=total_pages,
    )
    return response_base.page(data=page_data)


@limit_up_router.get(
    "/stats",
    response_model=ResponseModel[LimitUpStats],
    summary="获取当日涨停统计（含炸板家数）",
    dependencies=[Depends(require_permission("stock:limit_up:list"))],
)
async def get_limit_up_stats(
    date: str | None = Query(None, description="快照日期 YYYY-MM-DD，为空取最新"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """获取当日涨停统计（涨停家数、市场板块分布、连板高度、炸板家数等，涨停口径仅含封板股）"""
    data = await LimitUpService.get_stats(db, date)
    return response_base.success(data=data)


@limit_up_router.get(
    "/dates",
    response_model=ResponseModel[list[str]],
    summary="获取可回看日期列表",
    dependencies=[Depends(require_permission("stock:limit_up:list"))],
)
async def get_limit_up_dates(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """获取涨停/炸板股池所有可回看的快照日期（降序）"""
    dates = await LimitUpService.get_dates(db)
    return response_base.success(data=[d.isoformat() for d in dates])
