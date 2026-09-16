#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略回测相关接口

回测语义：信号源为回放已记录的真实 AI 信号（business_strategy_signal），
不做 LLM 逐日重放——行情/资讯快照是当前值，逐日重放存在前视偏差。
信号统一在产生日之后的第一个交易日按开盘价成交（先卖后买再调整），
止损/止盈/回撤止盈/涨停暂缓/T+1 与实盘交易引擎语义一致。
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, ResponsePageDataModel, response_base
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.backtest.schemas.backtest import (
    BacktestRunRequest,
    BacktestItem,
    BacktestDetail,
    BacktestTradeItem,
)
from modules.backtest.services.backtest_service import BacktestService

logger = logging.getLogger(__name__)

backtest_router = APIRouter(prefix="", tags=["AI助手/策略回测"])


def _page_data(records, page, page_size, total):
    return ResponsePageDataModel(
        records=records, page=page, page_size=page_size, total=total,
        total_pages=(total + page_size - 1) // page_size if page_size else 0,
    )


@backtest_router.post(
    "/run",
    response_model=ResponseModel[BacktestItem],
    summary="发起策略回测（异步，立即返回 running 记录）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def run_backtest(
    req: BacktestRunRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """发起一次策略回测：校验策略与日期区间（≤3 年）后创建 running 记录并立即返回，
    回测在后台任务中执行（回放该策略区间内已记录的真实 AI 信号，非 LLM 逐日重放）；
    同策略存在 running 回测时拒绝并发"""
    backtest = await BacktestService.submit(db, req)
    return response_base.success(
        data=BacktestItem.model_validate(backtest),
        msg="已提交回测，执行完成后可通过详情接口查看结果",
    )


@backtest_router.get(
    "/list",
    response_model=ResponseModel[ResponsePageDataModel[BacktestItem]],
    summary="分页获取回测列表（按创建时间倒序）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_backtest_list(
    strategy_id: int | None = Query(None, description="策略 ID 过滤"),
    status: str | None = Query(None, description="状态过滤：running/success/failed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """分页查询回测任务列表"""
    items, total = await BacktestService.get_list(db, strategy_id, status, page, page_size)
    return response_base.success(data=_page_data(items, page, page_size, total))


@backtest_router.get(
    "/{backtest_id}",
    response_model=ResponseModel[BacktestDetail],
    summary="获取回测详情（含绩效汇总与净值曲线）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_backtest_detail(
    backtest_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """获取回测详情：result 为绩效汇总（收益率/回撤/夏普/胜率/warnings），
    equity_curve 为每日净值点 {date, equity, cash, market_value}"""
    backtest = await BacktestService.get_by_id(db, backtest_id)
    return response_base.success(data=BacktestDetail.model_validate(backtest))


@backtest_router.get(
    "/{backtest_id}/trades",
    response_model=ResponseModel[ResponsePageDataModel[BacktestTradeItem]],
    summary="分页获取回测成交明细（按成交日期升序）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_backtest_trades(
    backtest_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """分页查询回测逐笔成交明细"""
    items, total = await BacktestService.get_trades(db, backtest_id, page, page_size)
    return response_base.success(data=_page_data(items, page, page_size, total))


@backtest_router.delete(
    "/{backtest_id}",
    response_model=ResponseModel,
    summary="删除回测记录（软删除，运行中不可删除）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def delete_backtest(
    backtest_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """软删除回测记录；running 状态拒绝删除"""
    await BacktestService.delete(db, backtest_id)
    await db.commit()
    return response_base.success(msg="删除成功")
