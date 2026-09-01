#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""企业财报获取与 AI 解读相关接口"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, ResponsePageDataModel, response_base
from core.response.response_code import CustomErrorCode
from core.exception.errors import CustomError
from database.models.business.financial import (
    BusinessFinancialReport,
    BusinessFinancialInterpretation,
)
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.financial.services.financial_service import FinancialService
from modules.financial.services.financial_fetcher import _norm_code
from modules.financial.schemas.financial import (
    StockCodeQuery,
    RatingQuery,
    DirectionQuery,
    FinancialReportItem,
    FinancialInterpretItem,
    FinancialInterpretDetailItem,
    FinancialInterpretSubmitResult,
)

logger = logging.getLogger(__name__)

financial_router = APIRouter(prefix="", tags=["AI助手/财报解读"])


def _page_data(records, page, page_size, total):
    return ResponsePageDataModel(
        records=records, page=page, page_size=page_size, total=total,
        total_pages=(total + page_size - 1) // page_size if page_size else 0,
    )


@financial_router.get(
    "/reports/{stock_code}",
    response_model=ResponseModel[list[FinancialReportItem]],
    summary="获取个股财报关键指标（库内近几期，report_period 倒序）",
    dependencies=[Depends(require_permission("financial:list"))],
)
async def get_financial_reports(
    stock_code: str,
    limit: int = Query(8, ge=1, le=24),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    code = _norm_code(stock_code)
    reports = await FinancialService.get_reports(db, code, limit)
    return response_base.success(
        data=[FinancialReportItem.model_validate(r) for r in reports]
    )


@financial_router.post(
    "/interpretations/{stock_code}",
    response_model=ResponseModel[FinancialInterpretSubmitResult],
    summary="触发个股财报 AI 解读（异步：自动补抓财报后立即返回，结果轮询解读记录）",
    dependencies=[Depends(require_permission("financial:run"))],
)
async def submit_financial_interpretation(
    stock_code: str,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """提交财报 AI 解读：库内无财报时自动抓取补齐，创建 running 记录后立即返回，
    LLM 解读在后台任务中进行"""
    interpretation_id = await FinancialService.submit_interpretation(
        db, stock_code, trigger_type="manual",
    )
    return response_base.success(
        data=FinancialInterpretSubmitResult(interpretation_id=interpretation_id),
        msg="已提交解读，请稍后查看结果",
    )


@financial_router.get(
    "/interpretations",
    response_model=ResponseModel[ResponsePageDataModel[FinancialInterpretItem]],
    summary="分页获取财报解读记录（可按股票/本期评级/下期预测方向筛选，持仓股定时自动解读 + 手动记录）",
    dependencies=[Depends(require_permission("financial:list"))],
)
async def get_financial_interpretations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    stock_code: StockCodeQuery = None,
    quality_rating: RatingQuery = None,
    forecast_direction: DirectionQuery = None,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    conditions = [BusinessFinancialInterpretation.deleted_at.is_(None)]
    if stock_code:
        conditions.append(BusinessFinancialInterpretation.stock_code == stock_code)
    if quality_rating:
        conditions.append(
            BusinessFinancialInterpretation.parsed_result["quality_rating"].as_string() == quality_rating
        )
    if forecast_direction:
        conditions.append(
            BusinessFinancialInterpretation.parsed_result["forecast"]["direction"].as_string() == forecast_direction
        )
    count_result = await db.execute(
        select(func.count()).select_from(BusinessFinancialInterpretation).where(*conditions)
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(BusinessFinancialInterpretation)
        .where(*conditions)
        .order_by(BusinessFinancialInterpretation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [FinancialInterpretItem.model_validate(row) for row in result.scalars().all()]
    return response_base.success(data=_page_data(items, page, page_size, total))


@financial_router.get(
    "/interpretations/detail/{interpretation_id}",
    response_model=ResponseModel[FinancialInterpretDetailItem],
    summary="获取财报解读详情（含 AI 报告原文）",
    dependencies=[Depends(require_permission("financial:list"))],
)
async def get_financial_interpretation_detail(
    interpretation_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(BusinessFinancialInterpretation).where(
            BusinessFinancialInterpretation.id == interpretation_id,
            BusinessFinancialInterpretation.deleted_at.is_(None),
        )
    )
    interp = result.scalar_one_or_none()
    if interp is None:
        raise CustomError(
            error=CustomErrorCode.FINANCIAL_INTERPRET_NOT_FOUND,
            msg="财报解读记录不存在或已删除",
        )
    return response_base.success(data=FinancialInterpretDetailItem.model_validate(interp))
