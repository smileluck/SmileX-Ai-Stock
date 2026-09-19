#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 分析策略相关接口
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import (
    ResponseModel,
    ResponsePageDataModel,
    ResponsePageModel,
    response_base,
)
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.common.schemas.page import PageRequest, get_page_params, get_paginated_results
from modules.strategy.services.strategy_service import StrategyService
from modules.strategy.schemas.strategy import (
    StrategyCreateRequest,
    StrategyExportData,
    StrategyImportRequest,
    StrategyItem,
    StrategyRunSubmitResult,
    StrategyRunItem,
    TemplateItem,
    TemplatePublishRequest,
)

strategy_router = APIRouter(prefix="/strategies", tags=["AI助手/AI分析"])


# ----------------------------------------------------------------------
# 策略管理
# ----------------------------------------------------------------------
@strategy_router.get(
    "",
    response_model=ResponsePageModel[StrategyItem],
    summary="分页获取策略列表",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_strategy_list(
    name: str | None = Query(None, description="策略名称模糊查询"),
    status: bool | None = Query(None, description="状态过滤"),
    category: str | None = Query(None, description="策略分类过滤：pre_market_auction/noon/tail/blue_chip/general"),
    page_params: PageRequest = Depends(get_page_params),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """分页获取策略列表（创建时间倒序），支持名称模糊/状态/分类过滤"""
    query = StrategyService.build_list_query(name, status, category)
    page_data = await get_paginated_results(db, page_params, query, StrategyItem)
    return response_base.page(data=page_data)


@strategy_router.post(
    "",
    response_model=ResponseModel[StrategyItem],
    summary="创建策略",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def create_strategy(
    req: StrategyCreateRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    item = await StrategyService.create(db, req)
    return response_base.success(data=item, msg="创建成功")


@strategy_router.put(
    "/{strategy_id}",
    response_model=ResponseModel[StrategyItem],
    summary="更新策略",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def update_strategy(
    strategy_id: int,
    req: StrategyCreateRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    item = await StrategyService.update(db, strategy_id, req)
    return response_base.success(data=item, msg="更新成功")


@strategy_router.delete(
    "/{strategy_id}",
    response_model=ResponseModel,
    summary="删除策略（软删除）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def delete_strategy(
    strategy_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await StrategyService.delete(db, strategy_id)
    return response_base.success(msg="删除成功")


# ----------------------------------------------------------------------
# 策略模板市场（固定路径须声明在 /{strategy_id} 之前）
# ----------------------------------------------------------------------
@strategy_router.get(
    "/templates",
    response_model=ResponsePageModel[TemplateItem],
    summary="模板市场列表（已发布模板 + 系统预置策略，附克隆次数与最近回测摘要）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_template_list(
    page_params: PageRequest = Depends(get_page_params),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """模板市场：is_template=True 或 is_preset=True 的策略，按创建时间倒序；
    每条附带 tags/source_id、克隆次数（存活克隆件计数）、最近一次 success 回测的
    绩效摘要（total_return_pct/max_drawdown_pct/win_rate/trade_count 与回测区间，无则 null）"""
    items, total = await StrategyService.list_templates(
        db, page_params.page, page_params.page_size
    )
    page_data = ResponsePageDataModel(
        records=items,
        page=page_params.page,
        page_size=page_params.page_size,
        total=total,
        total_pages=(total + page_params.page_size - 1) // page_params.page_size,
    )
    return response_base.page(data=page_data)


@strategy_router.post(
    "/import",
    response_model=ResponseModel[StrategyItem],
    summary="导入策略（可移植 JSON，schema_version 仅接受 1，新建为停用状态）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def import_strategy(
    req: StrategyImportRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """导入策略 JSON（来自导出接口）：逐项校验分类/时段/股票池结构/百分比范围，
    schema_version 非法或字段校验失败返回 11509；name 冲突自动追加序号；
    新策略 is_preset/is_template=False、status 停用"""
    item = await StrategyService.import_strategy(db, req)
    return response_base.success(data=item, msg="导入成功（默认停用，请确认配置后手动启用）")


@strategy_router.post(
    "/{strategy_id}/clone",
    response_model=ResponseModel[StrategyItem],
    summary="克隆策略（默认停用，名称追加「（副本）」，重名追加序号）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def clone_strategy(
    strategy_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """克隆策略：prompt/股票池/时段/风控参数/tags 原样复制，is_preset/is_template 重置为 False，
    source_id 指向原策略；克隆件默认停用（实盘引擎只跑启用策略），待确认后手动启用"""
    item = await StrategyService.clone(db, strategy_id)
    return response_base.success(data=item, msg="克隆成功（默认停用，请确认配置后手动启用）")


@strategy_router.post(
    "/{strategy_id}/publish",
    response_model=ResponseModel[StrategyItem],
    summary="发布为模板（可选覆盖 tags）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def publish_strategy(
    strategy_id: int,
    req: TemplatePublishRequest | None = None,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """发布策略为模板（is_template=True，is_preset 策略也允许发布）；body 传 tags 时覆盖更新标签"""
    item = await StrategyService.set_template(db, strategy_id, True, req.tags if req else None)
    return response_base.success(data=item, msg="已发布为模板")


@strategy_router.post(
    "/{strategy_id}/unpublish",
    response_model=ResponseModel[StrategyItem],
    summary="下架模板（可选覆盖 tags）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def unpublish_strategy(
    strategy_id: int,
    req: TemplatePublishRequest | None = None,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """下架模板（is_template=False）；body 传 tags 时覆盖更新标签"""
    item = await StrategyService.set_template(db, strategy_id, False, req.tags if req else None)
    return response_base.success(data=item, msg="已下架模板")


@strategy_router.get(
    "/{strategy_id}/export",
    response_model=ResponseModel[StrategyExportData],
    summary="导出策略为可移植 JSON（schema_version=1，不含 id/状态/时间戳）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def export_strategy(
    strategy_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """导出策略配置：{schema_version, name, description, category, prompt_template,
    stock_pool, execute_periods, max_positions, stop_loss_pct, take_profit_pct,
    trailing_drawdown_pct, tags, strategy_type, rule_config}，可经导入接口跨环境迁移；
    schema_version 保持 1（新增字段向后兼容，旧格式 JSON 缺省按 prompt 型导入）"""
    data = await StrategyService.export_strategy(db, strategy_id)
    return response_base.success(data=data)


# ----------------------------------------------------------------------
# 策略执行
# ----------------------------------------------------------------------
@strategy_router.post(
    "/{strategy_id}/run",
    response_model=ResponseModel[StrategyRunSubmitResult],
    summary="手动触发一次策略执行（异步，立即返回）",
    dependencies=[Depends(require_permission("strategy:run"))],
)
async def run_strategy(
    strategy_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """手动执行策略：创建执行记录后立即返回，分析/评估在后台进行；
    prompt 型走 LLM 分析，rule 型走规则评估；
    产出的买卖信号由每分钟交易引擎按实时价执行模拟买卖"""
    run_id = await StrategyService.submit_run(
        db, strategy_id, run_period="manual", trigger_type="manual"
    )
    return response_base.success(
        data=StrategyRunSubmitResult(run_id=run_id),
        msg="已提交执行，分析完成后信号将由交易引擎执行",
    )


@strategy_router.get(
    "/{strategy_id}/runs",
    response_model=ResponsePageModel[StrategyRunItem],
    summary="分页获取策略执行记录",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_strategy_runs(
    strategy_id: int,
    page_params: PageRequest = Depends(get_page_params),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """分页获取策略执行记录（创建时间倒序）"""
    query = StrategyService.build_runs_query(strategy_id)
    page_data = await get_paginated_results(db, page_params, query, StrategyRunItem)
    return response_base.page(data=page_data)
