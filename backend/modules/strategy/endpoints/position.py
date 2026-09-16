#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 分析策略持仓相关接口
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, ResponsePageDataModel, response_base
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.strategy.services.position_service import PositionService
from modules.strategy.services.strategy_service import StrategyService
from modules.strategy.schemas.strategy import (
    AttributionResult,
    EquityCurvePoint,
    PositionItem,
    PositionCloseRequest,
    TrackLogItem,
    StrategyStatsItem,
)

logger = logging.getLogger(__name__)

position_router = APIRouter(prefix="/positions", tags=["AI助手/AI分析"])

# 绩效深化统计（净值曲线 / 归因），独立于持仓 CRUD 子前缀
stats_router = APIRouter(prefix="/stats", tags=["AI助手/AI分析"])


def _page_data(records, page, page_size, total):
    return ResponsePageDataModel(
        records=records, page=page, page_size=page_size, total=total,
        total_pages=(total + page_size - 1) // page_size if page_size else 0,
    )


@position_router.get(
    "",
    response_model=ResponseModel[ResponsePageDataModel[PositionItem]],
    summary="分页获取持仓列表",
    dependencies=[Depends(require_permission("strategy:position:list"))],
)
async def get_positions(
    strategy_id: Optional[int] = Query(None, description="策略 ID 过滤"),
    status: Optional[str] = Query(None, description="持仓状态：holding/closed/cancelled"),
    stock_code: Optional[str] = Query(None, description="证券代码模糊查询"),
    start_time: Optional[str] = Query(None, description="建仓时间起（ISO 8601，如 2026-08-01T00:00:00）"),
    end_time: Optional[str] = Query(None, description="建仓时间止（ISO 8601）"),
    sort_by: Optional[str] = Query(
        None, description="排序列：buy_time/sell_time/pnl/return_rate；为空时默认持仓中在前+建仓时间倒序"
    ),
    sort_desc: bool = Query(False, description="是否倒序排序，配合 sort_by 使用"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    items, total = await PositionService.get_positions(
        db, strategy_id, status, stock_code,
        start_time, end_time, sort_by, sort_desc, page, page_size
    )
    return response_base.success(data=_page_data(items, page, page_size, total))


@position_router.post(
    "/track",
    response_model=ResponseModel[dict],
    summary="手动触发一次持仓跟踪",
    dependencies=[Depends(require_permission("strategy:position:list"))],
)
async def track_positions(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """刷新全部持仓最新价/浮盈，触发止损/止盈/目标价自动平仓"""
    result = await PositionService.track_positions(db)
    return response_base.success(data=result, msg="持仓跟踪完成")


@position_router.post(
    "/{position_id}/close",
    response_model=ResponseModel[PositionItem],
    summary="手动平仓",
    dependencies=[Depends(require_permission("strategy:position:close"))],
)
async def close_position(
    position_id: int,
    req: PositionCloseRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    item = await PositionService.close_position(db, position_id, req.price, req.reason)
    return response_base.success(data=item, msg="平仓成功")


@position_router.get(
    "/{position_id}/tracks",
    response_model=ResponseModel[list[TrackLogItem]],
    summary="获取持仓跟踪日志",
    dependencies=[Depends(require_permission("strategy:position:list"))],
)
async def get_position_tracks(
    position_id: int,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    items = await PositionService.get_tracks(db, position_id, limit)
    return response_base.success(data=items)


@position_router.get(
    "/stats",
    response_model=ResponseModel[list[StrategyStatsItem]],
    summary="获取策略回报率统计",
    dependencies=[Depends(require_permission("strategy:position:list"))],
)
async def get_stats(
    strategy_id: Optional[int] = Query(None, description="策略 ID 过滤，为空返回全部"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    items = await PositionService.get_stats(db, strategy_id)
    return response_base.success(data=items)


# ----------------------------------------------------------------------
# 绩效深化（净值曲线 / 归因）
# ----------------------------------------------------------------------
@stats_router.get(
    "/equity-curve",
    response_model=ResponseModel[list[EquityCurvePoint]],
    summary="策略模拟盘净值曲线（等权平均口径，基准 100）",
    dependencies=[Depends(require_permission("strategy:position:list"))],
)
async def get_equity_curve(
    strategy_id: int = Query(..., description="策略 ID"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """每日净值 = 当日处于持有期的全部持仓「当日最新已知浮盈%」等权平均 + 100；
    数据源为持仓表 + 跟踪日志（按日取最后一条、前向填充、卖出日锁定最终收益率），
    只输出有跟踪数据的日期"""
    items = await PositionService.get_equity_curve(db, strategy_id)
    return response_base.success(data=items)


@stats_router.get(
    "/attribution",
    response_model=ResponseModel[AttributionResult],
    summary="策略归因统计（按卖出原因 / 按建仓来源时段）",
    dependencies=[Depends(require_permission("strategy:position:list"))],
)
async def get_attribution(
    strategy_id: int = Query(..., description="策略 ID"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """by_sell_reason 仅统计已平仓持仓；by_run_period 按建仓归属（position.run_id →
    Run.run_period，存量无 run_id 归入 unknown），含 holding 持仓浮盈"""
    result = await PositionService.get_attribution(db, strategy_id)
    return response_base.success(data=result)
