#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 大盘/板块分析相关接口
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, ResponsePageDataModel, response_base
from core.response.response_code import CustomErrorCode
from core.exception.errors import CustomError
from database.models.business.analysis import BusinessAnalysisRun
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.analysis.services.analysis_executor import AnalysisExecutor
from modules.analysis.services.analysis_config_service import AnalysisConfigService
from modules.analysis.services.mainline_service import MainlineService
from modules.analysis.schemas.analysis import (
    ANALYSIS_TYPES,
    ANALYSIS_TYPE_NAMES,
    SESSION_TYPE_NAMES,
    VALID_TYPE_SESSIONS,
    AnalysisConfigItem,
    AnalysisConfigUpdateRequest,
    AnalysisRunDetailItem,
    AnalysisRunItem,
    AnalysisRunSubmitResult,
    NewsMainlinesResult,
)

logger = logging.getLogger(__name__)

analysis_router = APIRouter(prefix="", tags=["AI助手/大盘板块分析"])


def _validate_analysis_type(analysis_type: str) -> str:
    """校验分析类型：market-大盘，sector-板块，news-每日资讯"""
    if analysis_type not in ANALYSIS_TYPES:
        raise CustomError(
            error=CustomErrorCode.ANALYSIS_TYPE_INVALID,
            msg=f"分析类型非法，仅支持 {'/'.join(ANALYSIS_TYPE_NAMES.values())}",
        )
    return analysis_type


def _validate_session(analysis_type: str, session: str) -> str:
    """校验类型×时段合法组合：news 仅支持 morning/weekly，market/sector 仅支持 close/morning"""
    valid_sessions = VALID_TYPE_SESSIONS.get(analysis_type, ())
    if session not in valid_sessions:
        raise CustomError(
            error=CustomErrorCode.ANALYSIS_TYPE_INVALID,
            msg=f"分析时段非法，「{ANALYSIS_TYPE_NAMES.get(analysis_type, analysis_type)}」"
                f"仅支持 {'/'.join(SESSION_TYPE_NAMES[s] for s in valid_sessions)}",
        )
    return session


def _page_data(records, page, page_size, total):
    return ResponsePageDataModel(
        records=records, page=page, page_size=page_size, total=total,
        total_pages=(total + page_size - 1) // page_size if page_size else 0,
    )


# ----------------------------------------------------------------------
# 生成分析
# ----------------------------------------------------------------------
@analysis_router.post(
    "/{analysis_type}/run",
    response_model=ResponseModel[AnalysisRunSubmitResult],
    summary="手动触发生成大盘/板块 AI 分析（异步，立即返回）",
    dependencies=[Depends(require_permission("analysis:run"))],
)
async def run_analysis(
    analysis_type: str,
    session: str = Query("close", description="分析时段：close-收盘分析，morning-早盘分析，weekly-周度复盘（仅资讯分析）"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """手动生成分析：创建执行记录后立即返回，LLM 在后台生成，
    前端轮询 latest 或 runs 接口查看进度与结果"""
    _validate_analysis_type(analysis_type)
    _validate_session(analysis_type, session)
    run_id = await AnalysisExecutor.submit_run(
        db, analysis_type, trigger_type="manual", session=session,
    )
    return response_base.success(
        data=AnalysisRunSubmitResult(run_id=run_id),
        msg="已提交生成，请稍后查看分析结果",
    )


# ----------------------------------------------------------------------
# 分析策略配置
# ----------------------------------------------------------------------
@analysis_router.get(
    "/{analysis_type}/config",
    response_model=ResponseModel[AnalysisConfigItem],
    summary="获取分析策略配置（无记录时返回默认值：默认策略 + 明日研判开启）",
    dependencies=[Depends(require_permission("analysis:list"))],
)
async def get_analysis_config(
    analysis_type: str,
    session: str = Query("close", description="分析时段：close-收盘分析，morning-早盘分析，weekly-周度复盘（仅资讯分析）"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    _validate_analysis_type(analysis_type)
    _validate_session(analysis_type, session)
    config = await AnalysisConfigService.get_effective(db, analysis_type, session)
    return response_base.success(data=config)


@analysis_router.put(
    "/{analysis_type}/config",
    response_model=ResponseModel[AnalysisConfigItem],
    summary="保存分析策略配置（策略提示词 + 明日研判开关，下次生成时生效）",
    dependencies=[Depends(require_permission("analysis:strategy"))],
)
async def update_analysis_config(
    analysis_type: str,
    req: AnalysisConfigUpdateRequest,
    session: str = Query("close", description="分析时段：close-收盘分析，morning-早盘分析，weekly-周度复盘（仅资讯分析）"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    _validate_analysis_type(analysis_type)
    _validate_session(analysis_type, session)
    config = await AnalysisConfigService.update_config(db, analysis_type, req, session)
    return response_base.success(data=config, msg="保存成功，下次生成分析时生效")


# ----------------------------------------------------------------------
# 查询
# ----------------------------------------------------------------------
@analysis_router.get(
    "/{analysis_type}/latest",
    response_model=ResponseModel[AnalysisRunDetailItem | None],
    summary="获取最新一条分析（含报告原文，无记录时 data 为空）",
    dependencies=[Depends(require_permission("analysis:list"))],
)
async def get_latest_analysis(
    analysis_type: str,
    session: str = Query("close", description="分析时段：close-收盘分析，morning-早盘分析，weekly-周度复盘（仅资讯分析）"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    _validate_analysis_type(analysis_type)
    _validate_session(analysis_type, session)
    result = await db.execute(
        select(BusinessAnalysisRun)
        .where(
            BusinessAnalysisRun.analysis_type == analysis_type,
            BusinessAnalysisRun.session == session,
            BusinessAnalysisRun.deleted_at.is_(None),
        )
        .order_by(BusinessAnalysisRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return response_base.success(data=None)
    return response_base.success(data=AnalysisRunDetailItem.model_validate(run))


@analysis_router.get(
    "/{analysis_type}/runs",
    response_model=ResponseModel[ResponsePageDataModel[AnalysisRunItem]],
    summary="分页获取分析历史记录",
    dependencies=[Depends(require_permission("analysis:list"))],
)
async def get_analysis_runs(
    analysis_type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: str = Query("close", description="分析时段：close-收盘分析，morning-早盘分析，weekly-周度复盘（仅资讯分析）"),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    _validate_analysis_type(analysis_type)
    _validate_session(analysis_type, session)
    conditions = [
        BusinessAnalysisRun.analysis_type == analysis_type,
        BusinessAnalysisRun.session == session,
        BusinessAnalysisRun.deleted_at.is_(None),
    ]
    count_result = await db.execute(
        select(func.count()).select_from(BusinessAnalysisRun).where(*conditions)
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(BusinessAnalysisRun)
        .where(*conditions)
        .order_by(BusinessAnalysisRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [AnalysisRunItem.model_validate(row) for row in result.scalars().all()]
    return response_base.success(data=_page_data(items, page, page_size, total))


@analysis_router.get(
    "/news/mainlines",
    response_model=ResponseModel[NewsMainlinesResult],
    summary="获取长期主线聚合（LLM 主线分析 + 主线分组资讯）",
    dependencies=[Depends(require_permission("analysis:list"))],
)
async def get_news_mainlines(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """主线页数据：最近一次每日资讯分析（news/morning）的 mainlines
    + 注册表全量主线的近 7 天资讯分组（无数据的主线 count=0）"""
    data = await MainlineService.get_news_mainlines(db)
    return response_base.success(data=data)


@analysis_router.get(
    "/runs/{run_id}",
    response_model=ResponseModel[AnalysisRunDetailItem],
    summary="获取分析记录详情（含报告原文）",
    dependencies=[Depends(require_permission("analysis:list"))],
)
async def get_analysis_run_detail(
    run_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(BusinessAnalysisRun).where(
            BusinessAnalysisRun.id == run_id,
            BusinessAnalysisRun.deleted_at.is_(None),
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise CustomError(
            error=CustomErrorCode.ANALYSIS_RUN_NOT_FOUND,
            msg="分析记录不存在或已删除",
        )
    return response_base.success(data=AnalysisRunDetailItem.model_validate(run))
