#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 分析策略 CRUD 服务
"""
import logging

from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode
from database.models.business.strategy import BusinessAiStrategy
from modules.strategy.schemas.strategy import (
    EXECUTE_PERIODS,
    STRATEGY_CATEGORIES,
    STRATEGY_EXPORT_SCHEMA_VERSION,
    StrategyCreateRequest,
    StrategyExportData,
    StrategyImportRequest,
    StrategyItem,
    TemplateBacktestSummary,
    TemplateItem,
)

logger = logging.getLogger(__name__)


def _validate_periods(periods: list[str]) -> None:
    invalid = [p for p in periods if p not in EXECUTE_PERIODS]
    if invalid:
        raise CustomError(
            error=CustomErrorCode.STRATEGY_EXECUTE_FAILED,
            msg=f"不支持的执行时段: {invalid}，可选值: {list(EXECUTE_PERIODS)}",
        )


def _validate_category(category: str) -> None:
    if category not in STRATEGY_CATEGORIES:
        raise CustomError(
            error=CustomErrorCode.STRATEGY_EXECUTE_FAILED,
            msg=f"不支持的策略分类: {category}，可选值: {list(STRATEGY_CATEGORIES)}",
        )


class StrategyService:
    """AI 分析策略服务类"""

    @staticmethod
    async def get_by_id(db: AsyncSession, strategy_id: int) -> BusinessAiStrategy:
        result = await db.execute(
            select(BusinessAiStrategy).where(
                BusinessAiStrategy.id == strategy_id,
                BusinessAiStrategy.deleted_at.is_(None),
            )
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_NOT_FOUND,
                msg=f"策略 [{strategy_id}] 不存在",
            )
        return strategy

    @staticmethod
    async def get_list(
        db: AsyncSession,
        name: str | None = None,
        status: bool | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StrategyItem], int]:
        """分页查询策略列表，返回 (items, total)"""
        conditions = [BusinessAiStrategy.deleted_at.is_(None)]
        if name:
            conditions.append(BusinessAiStrategy.name.ilike(f"%{name}%"))
        if status is not None:
            conditions.append(BusinessAiStrategy.status == status)
        if category:
            conditions.append(BusinessAiStrategy.category == category)

        count_result = await db.execute(
            select(func.count()).select_from(BusinessAiStrategy).where(*conditions)
        )
        total = count_result.scalar() or 0

        result = await db.execute(
            select(BusinessAiStrategy)
            .where(*conditions)
            .order_by(BusinessAiStrategy.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            StrategyItem.model_validate(row) for row in result.scalars().all()
        ]
        return items, total

    @staticmethod
    async def get_enabled(db: AsyncSession) -> list[BusinessAiStrategy]:
        """获取全部启用策略（调度任务用）"""
        result = await db.execute(
            select(BusinessAiStrategy).where(
                BusinessAiStrategy.status == True,  # noqa: E712
                BusinessAiStrategy.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, req: StrategyCreateRequest) -> StrategyItem:
        _validate_periods(req.execute_periods)
        _validate_category(req.category)

        exist = await db.execute(
            select(BusinessAiStrategy.id).where(
                BusinessAiStrategy.name == req.name,
                BusinessAiStrategy.deleted_at.is_(None),
            )
        )
        if exist.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_NAME_EXIST,
                msg=f"策略名称 [{req.name}] 已存在",
            )

        strategy = BusinessAiStrategy(
            name=req.name,
            description=req.description,
            category=req.category,
            prompt_template=req.prompt_template,
            stock_pool=req.stock_pool,
            execute_periods=req.execute_periods,
            max_positions=req.max_positions,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
            trailing_drawdown_pct=req.trailing_drawdown_pct or None,
            status=req.status,
        )
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        return StrategyItem.model_validate(strategy)

    @staticmethod
    async def update(
        db: AsyncSession, strategy_id: int, req: StrategyCreateRequest
    ) -> StrategyItem:
        _validate_periods(req.execute_periods)
        _validate_category(req.category)
        strategy = await StrategyService.get_by_id(db, strategy_id)

        # 名称查重（排除自身）
        exist = await db.execute(
            select(BusinessAiStrategy.id).where(
                BusinessAiStrategy.name == req.name,
                BusinessAiStrategy.id != strategy_id,
                BusinessAiStrategy.deleted_at.is_(None),
            )
        )
        if exist.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_NAME_EXIST,
                msg=f"策略名称 [{req.name}] 已存在",
            )

        strategy.name = req.name
        strategy.description = req.description
        strategy.category = req.category
        strategy.prompt_template = req.prompt_template
        strategy.stock_pool = req.stock_pool
        strategy.execute_periods = req.execute_periods
        strategy.max_positions = req.max_positions
        strategy.stop_loss_pct = req.stop_loss_pct
        strategy.take_profit_pct = req.take_profit_pct
        strategy.trailing_drawdown_pct = req.trailing_drawdown_pct or None
        strategy.status = req.status
        await db.commit()
        await db.refresh(strategy)
        return StrategyItem.model_validate(strategy)

    @staticmethod
    async def delete(db: AsyncSession, strategy_id: int) -> None:
        strategy = await StrategyService.get_by_id(db, strategy_id)
        strategy.soft_delete()
        await db.commit()

    @staticmethod
    async def toggle_status(db: AsyncSession, strategy_id: int, status: bool) -> StrategyItem:
        strategy = await StrategyService.get_by_id(db, strategy_id)
        strategy.status = status
        await db.commit()
        await db.refresh(strategy)
        return StrategyItem.model_validate(strategy)

    # ------------------------------------------------------------------
    # 策略模板市场（克隆 / 发布 / 模板列表 / 导出 / 导入）
    # ------------------------------------------------------------------
    @staticmethod
    async def _name_exists(db: AsyncSession, name: str) -> bool:
        result = await db.execute(
            select(BusinessAiStrategy.id).where(
                BusinessAiStrategy.name == name,
                BusinessAiStrategy.deleted_at.is_(None),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def clone(db: AsyncSession, strategy_id: int) -> StrategyItem:
        """克隆策略：配置原样复制（含 tags），source_id 指向原策略，
        is_preset/is_template 重置为 False，默认停用（待用户确认后手动启用）。
        名称取「原名（副本）」，重名时追加序号「（副本2）/（副本3）…」"""
        source = await StrategyService.get_by_id(db, strategy_id)

        base = f"{source.name}（副本）"
        name = base
        seq = 2
        while await StrategyService._name_exists(db, name):
            name = f"{source.name}（副本{seq}）"
            seq += 1

        strategy = BusinessAiStrategy(
            name=name,
            description=source.description,
            category=source.category,
            is_preset=False,
            is_template=False,
            source_id=source.id,
            tags=list(source.tags) if source.tags else None,
            prompt_template=source.prompt_template,
            stock_pool=dict(source.stock_pool) if source.stock_pool else None,
            execute_periods=list(source.execute_periods) if source.execute_periods else None,
            max_positions=source.max_positions,
            stop_loss_pct=source.stop_loss_pct,
            take_profit_pct=source.take_profit_pct,
            trailing_drawdown_pct=source.trailing_drawdown_pct,
            status=False,
        )
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        logger.info("策略已克隆: %s -> %s(%s)", source.name, name, strategy.id)
        return StrategyItem.model_validate(strategy)

    @staticmethod
    async def set_template(
        db: AsyncSession, strategy_id: int, is_template: bool, tags: Optional[list[str]] = None
    ) -> StrategyItem:
        """发布/下架模板：翻转 is_template；tags 传入时覆盖更新"""
        strategy = await StrategyService.get_by_id(db, strategy_id)
        strategy.is_template = is_template
        if tags is not None:
            strategy.tags = [t.strip() for t in tags if t.strip()] or None
        await db.commit()
        await db.refresh(strategy)
        return StrategyItem.model_validate(strategy)

    @staticmethod
    async def list_templates(
        db: AsyncSession, page: int = 1, page_size: int = 20
    ) -> tuple[list[TemplateItem], int]:
        """模板市场列表：is_template 或 is_preset 的策略（创建时间倒序），
        每条附带克隆次数与最近一次 success 回测的绩效摘要"""
        from database.models.business.backtest import BusinessBacktest

        conditions = [
            BusinessAiStrategy.deleted_at.is_(None),
            or_(BusinessAiStrategy.is_template == True, BusinessAiStrategy.is_preset == True),  # noqa: E712
        ]
        count_result = await db.execute(
            select(func.count()).select_from(BusinessAiStrategy).where(*conditions)
        )
        total = count_result.scalar() or 0
        result = await db.execute(
            select(BusinessAiStrategy)
            .where(*conditions)
            .order_by(BusinessAiStrategy.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        strategies = list(result.scalars().all())
        if not strategies:
            return [], total
        ids = [s.id for s in strategies]

        # 克隆次数（含已软删除克隆件？否——只统计存活克隆）
        clone_rows = await db.execute(
            select(BusinessAiStrategy.source_id, func.count())
            .where(
                BusinessAiStrategy.source_id.in_(ids),
                BusinessAiStrategy.deleted_at.is_(None),
            )
            .group_by(BusinessAiStrategy.source_id)
        )
        clone_counts = dict(clone_rows.all())

        # 最近一次 success 回测（批量取回后按策略取最新一条）
        bt_rows = await db.execute(
            select(BusinessBacktest)
            .where(
                BusinessBacktest.strategy_id.in_(ids),
                BusinessBacktest.status == "success",
                BusinessBacktest.deleted_at.is_(None),
            )
            .order_by(BusinessBacktest.created_at.desc())
        )
        last_bt: dict[int, BusinessBacktest] = {}
        for bt in bt_rows.scalars().all():
            if bt.strategy_id not in last_bt:
                last_bt[bt.strategy_id] = bt

        items = []
        for s in strategies:
            item = TemplateItem.model_validate(s)
            item.clone_count = clone_counts.get(s.id, 0)
            bt = last_bt.get(s.id)
            if bt:
                r = bt.result or {}
                item.last_backtest = TemplateBacktestSummary(
                    start_date=bt.start_date,
                    end_date=bt.end_date,
                    total_return_pct=r.get("total_return_pct"),
                    max_drawdown_pct=r.get("max_drawdown_pct"),
                    win_rate=r.get("win_rate"),
                    trade_count=r.get("trade_count"),
                )
            items.append(item)
        return items, total

    @staticmethod
    async def export_strategy(db: AsyncSession, strategy_id: int) -> StrategyExportData:
        """导出策略为可移植 JSON（不含 id/状态/时间戳，附 schema_version）"""
        strategy = await StrategyService.get_by_id(db, strategy_id)
        return StrategyExportData(
            name=strategy.name,
            description=strategy.description,
            category=strategy.category,
            prompt_template=strategy.prompt_template,
            stock_pool=strategy.stock_pool,
            execute_periods=strategy.execute_periods,
            max_positions=strategy.max_positions,
            stop_loss_pct=strategy.stop_loss_pct,
            take_profit_pct=strategy.take_profit_pct,
            trailing_drawdown_pct=strategy.trailing_drawdown_pct,
            tags=strategy.tags,
        )

    @staticmethod
    async def import_strategy(db: AsyncSession, req: StrategyImportRequest) -> StrategyItem:
        """导入策略 JSON 新建策略：is_preset/is_template=False、默认停用、
        name 冲突时追加序号「（2）/（3）…」"""
        if req.schema_version != STRATEGY_EXPORT_SCHEMA_VERSION:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_IMPORT_INVALID,
                msg=f"不支持的 schema_version: {req.schema_version}，当前仅支持 {STRATEGY_EXPORT_SCHEMA_VERSION}",
            )
        try:
            _validate_category(req.category)
            _validate_periods(req.execute_periods)
            _validate_stock_pool(req.stock_pool)
        except CustomError as e:
            # 统一归为导入非法（保留原始中文说明）
            raise CustomError(error=CustomErrorCode.STRATEGY_IMPORT_INVALID, msg=e.msg)

        name = req.name.strip()
        candidate = name
        seq = 2
        while await StrategyService._name_exists(db, candidate):
            candidate = f"{name}（{seq}）"
            seq += 1

        strategy = BusinessAiStrategy(
            name=candidate,
            description=req.description,
            category=req.category,
            is_preset=False,
            is_template=False,
            tags=[t.strip() for t in req.tags if t.strip()] if req.tags else None,
            prompt_template=req.prompt_template,
            stock_pool=req.stock_pool,
            execute_periods=req.execute_periods,
            max_positions=req.max_positions,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
            trailing_drawdown_pct=req.trailing_drawdown_pct or None,
            status=False,
        )
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        logger.info("策略已导入: %s(%s)", candidate, strategy.id)
        return StrategyItem.model_validate(strategy)


def _validate_stock_pool(pool: Optional[dict]) -> None:
    """股票池结构校验：应为 {"codes": ["600519", ...]}（导入用）"""
    if pool is None:
        return
    codes = pool.get("codes") if isinstance(pool, dict) else None
    if not isinstance(codes, list) or any(not isinstance(c, str) or not c.strip() for c in codes):
        raise CustomError(
            error=CustomErrorCode.STRATEGY_IMPORT_INVALID,
            msg='stock_pool 结构非法，应为 {"codes": ["600519", ...]}',
        )
