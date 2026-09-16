#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略回测服务：CRUD + 发起回测（异步执行）

回测语义：回放已记录的真实 AI 信号（business_strategy_signal），
不做 LLM 逐日重放（行情/资讯快照是当前值，重放存在前视偏差）。
"""
import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode
from database.models.business.backtest import BusinessBacktest, BusinessBacktestTrade
from modules.backtest.schemas.backtest import (
    BacktestItem,
    BacktestRunRequest,
    BacktestTradeItem,
    MAX_BACKTEST_YEARS,
)
from modules.strategy.services.strategy_service import StrategyService

logger = logging.getLogger(__name__)


class BacktestService:
    """策略回测服务类"""

    # ------------------------------------------------------------------
    # 发起回测（异步：落库即返回，后台任务执行）
    # ------------------------------------------------------------------
    @staticmethod
    async def submit(db: AsyncSession, req: BacktestRunRequest) -> BusinessBacktest:
        """创建回测任务并提交后台执行，立即返回 running 状态的记录。

        校验：策略存在、日期合法且 start < end、区间不超过 3 年；
        并发守卫：同策略存在 running 状态回测时拒绝。
        """
        strategy = await StrategyService.get_by_id(db, req.strategy_id)

        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(req.end_date, "%Y-%m-%d").date()
        if start >= end:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg="回测开始日期必须早于结束日期",
            )
        if (end - start).days > MAX_BACKTEST_YEARS * 366:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg=f"回测区间不能超过 {MAX_BACKTEST_YEARS} 年",
            )

        dup = await db.execute(
            select(BusinessBacktest.id).where(
                BusinessBacktest.strategy_id == strategy.id,
                BusinessBacktest.status == "running",
                BusinessBacktest.deleted_at.is_(None),
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_RUNNING_CONFLICT,
                msg="该策略有正在运行的回测，请稍后再试",
            )

        backtest = BusinessBacktest(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            slippage_pct=req.slippage_pct,
            commission_pct=req.commission_pct,
            stamp_tax_pct=req.stamp_tax_pct,
            status="running",
        )
        db.add(backtest)
        await db.commit()  # expire_on_commit=False，flush 后 backtest.id 可直接取用

        from modules.backtest.services.backtest_runner import BacktestRunner
        BacktestRunner.spawn(backtest.id)
        logger.info(
            "已提交回测: strategy=%s backtest_id=%s range=%s~%s",
            strategy.name, backtest.id, req.start_date, req.end_date,
        )
        return backtest

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @staticmethod
    async def get_by_id(db: AsyncSession, backtest_id: int) -> BusinessBacktest:
        result = await db.execute(
            select(BusinessBacktest).where(
                BusinessBacktest.id == backtest_id,
                BusinessBacktest.deleted_at.is_(None),
            )
        )
        backtest = result.scalar_one_or_none()
        if not backtest:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_NOT_FOUND,
                msg=f"回测记录 [{backtest_id}] 不存在",
            )
        return backtest

    @staticmethod
    async def get_list(
        db: AsyncSession,
        strategy_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[BacktestItem], int]:
        """分页查询回测列表（按创建时间倒序），返回 (items, total)"""
        conditions = [BusinessBacktest.deleted_at.is_(None)]
        if strategy_id:
            conditions.append(BusinessBacktest.strategy_id == strategy_id)
        if status:
            conditions.append(BusinessBacktest.status == status)

        count_result = await db.execute(
            select(func.count()).select_from(BusinessBacktest).where(*conditions)
        )
        total = count_result.scalar() or 0
        result = await db.execute(
            select(BusinessBacktest)
            .where(*conditions)
            .order_by(BusinessBacktest.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [BacktestItem.model_validate(row) for row in result.scalars().all()]
        return items, total

    @staticmethod
    async def get_trades(
        db: AsyncSession, backtest_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[BacktestTradeItem], int]:
        """分页查询回测成交明细（按成交日期+ID 升序），返回 (items, total)"""
        await BacktestService.get_by_id(db, backtest_id)
        conditions = [
            BusinessBacktestTrade.backtest_id == backtest_id,
            BusinessBacktestTrade.deleted_at.is_(None),
        ]
        count_result = await db.execute(
            select(func.count()).select_from(BusinessBacktestTrade).where(*conditions)
        )
        total = count_result.scalar() or 0
        result = await db.execute(
            select(BusinessBacktestTrade)
            .where(*conditions)
            .order_by(BusinessBacktestTrade.trade_date, BusinessBacktestTrade.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [BacktestTradeItem.model_validate(row) for row in result.scalars().all()]
        return items, total

    # ------------------------------------------------------------------
    # 删除（软删除，运行中拒绝）
    # ------------------------------------------------------------------
    @staticmethod
    async def delete(db: AsyncSession, backtest_id: int) -> None:
        backtest = await BacktestService.get_by_id(db, backtest_id)
        if backtest.status == "running":
            raise CustomError(
                error=CustomErrorCode.BACKTEST_RUNNING_CONFLICT,
                msg="回测正在运行中，不可删除",
            )
        backtest.soft_delete()
        await db.flush()
