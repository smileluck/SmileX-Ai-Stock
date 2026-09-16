#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
因子管理相关接口

因子来源：预置开源公式因子（迁移种子，source=preset）+ 在线导入（source=imported）+ 手工自建（custom）。
公式 DSL 经 ast 白名单安全求值（禁止 eval/exec），字段为日线 OHLCV：
open/high/low/close/volume/amount/preclose/pct_chg/vwap；
时间序列函数 REF/MA/SUM/MAX/MIN/STD/DELTA/CORR/COUNT，标量函数 ABS/LOG/SQRT/SIGN/IF，
截面函数 RANK（仅顶层或算术/比较内，universe 内归一化排名，值大→近 1）。
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_manager import get_session
from core.response import ResponseModel, ResponsePageDataModel, response_base
from modules.admin.deps.auth.user_manager import current_user
from modules.admin.deps.auth.permission import require_permission
from modules.factor.schemas.factor import (
    FactorCalcRequest,
    FactorCalcResponse,
    FactorCreateRequest,
    FactorImportRequest,
    FactorImportResult,
    FactorItem,
    FactorScreenRequest,
    FactorScreenResponse,
    FactorUpdateRequest,
    SavePoolRequest,
    SavePoolResponse,
)
from modules.factor.services.factor_calc import FactorCalcService
from modules.factor.services.factor_service import FactorService

logger = logging.getLogger(__name__)

factor_router = APIRouter(prefix="", tags=["AI助手/因子管理"])


def _page_data(records, page, page_size, total):
    return ResponsePageDataModel(
        records=records, page=page, page_size=page_size, total=total,
        total_pages=(total + page_size - 1) // page_size if page_size else 0,
    )


@factor_router.get(
    "/list",
    response_model=ResponseModel[ResponsePageDataModel[FactorItem]],
    summary="分页获取因子列表（category/source/keyword 过滤）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_factor_list(
    category: str | None = Query(None, description="分类过滤，如 price/momentum/volume/volatility"),
    source: str | None = Query(None, description="来源过滤：preset/imported/custom"),
    keyword: str | None = Query(None, description="关键字（匹配名称或代码）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """分页查询因子列表（按创建时间倒序）"""
    items, total = await FactorService.get_list(db, category, source, keyword, page, page_size)
    return response_base.success(data=_page_data(items, page, page_size, total))


@factor_router.post(
    "/import",
    response_model=ResponseModel[FactorImportResult],
    summary="在线导入因子（URL 或粘贴 JSON，逐条校验，冲突跳过）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def import_factors(
    req: FactorImportRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """从 URL 或粘贴的 JSON 导入因子（source=imported）。

    因子 JSON 格式约定（数组或单个对象）：
    [{"name": "因子名称", "code": "唯一代码", "category": "分类(可选)",
      "formula": "DSL 公式", "description": "说明(可选)", "source_url": "来源链接(可选)"}]

    逐条校验公式合法性与 code 唯一性（含本批次内重复），非法/冲突条目跳过；
    返回 {imported, skipped, errors[]}，errors 为逐条失败原因。
    """
    result = await FactorService.import_factors(db, req)
    await db.commit()
    return response_base.success(
        data=FactorImportResult(**result),
        msg=f"导入完成：成功 {result['imported']} 条，跳过 {result['skipped']} 条",
    )


@factor_router.post(
    "/calc",
    response_model=ResponseModel[FactorCalcResponse],
    summary="计算因子值（对给定股票池，取目标日值）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def calc_factor(
    req: FactorCalcRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """对 codes 中各股计算因子在目标日的值（end_date 默认今天，取之前最后一个交易日；
    lookback 为回看交易日数，供 MA/STD 等窗口函数使用）；
    历史序列不足或结果为 NaN 的股票跳过并记入 warnings"""
    result = await FactorCalcService.calc(db, req)
    return response_base.success(data=FactorCalcResponse(**result))


@factor_router.post(
    "/screen",
    response_model=ResponseModel[FactorScreenResponse],
    summary="选股器（多条件 AND，结果可存为策略股票池）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def screen_stocks(
    req: FactorScreenRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """按条件筛选股票池：codes 或 strategy_id（用其股票池）二选一，**不支持全市场选股**；
    条件间为 AND，op=top_n 表示按该因子值降序取前 N 名；
    返回命中股票的各因子值（factor_values 键为因子 code，无法计算时为 None）"""
    result = await FactorCalcService.screen(db, req)
    return response_base.success(data=FactorScreenResponse(**result))


@factor_router.post(
    "/screen/save-pool",
    response_model=ResponseModel[SavePoolResponse],
    summary="将选股结果保存为策略股票池（覆盖式）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def save_screen_pool(
    req: SavePoolRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """覆盖 strategy.stock_pool = {"codes": [...]}；策略不存在时报错"""
    result = await FactorCalcService.save_pool(db, req)
    await db.commit()
    return response_base.success(data=SavePoolResponse(**result), msg="股票池已保存")


@factor_router.post(
    "/",
    response_model=ResponseModel[FactorItem],
    summary="创建因子（手工自建，source=custom）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def create_factor(
    req: FactorCreateRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """创建自定义因子：公式经白名单 DSL 校验，code 全局唯一。

    实际路径为 /admin/factor/（FastAPI 不允许空前缀+空路径组合；
    请求 /admin/factor 会被 307 重定向到带尾斜杠路径，语义一致）"""
    factor = await FactorService.create(db, req)
    await db.commit()
    return response_base.success(data=FactorItem.model_validate(factor), msg="创建成功")


@factor_router.get(
    "/{factor_id}",
    response_model=ResponseModel[FactorItem],
    summary="获取因子详情",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def get_factor_detail(
    factor_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """获取因子详情（含公式与来源信息）"""
    factor = await FactorService.get_by_id(db, factor_id)
    return response_base.success(data=FactorItem.model_validate(factor))


@factor_router.put(
    "/{factor_id}",
    response_model=ResponseModel[FactorItem],
    summary="更新因子（code 不可改；预置因子可停用）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def update_factor(
    factor_id: int,
    req: FactorUpdateRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """按传入字段更新因子；公式变更需重新通过白名单校验；
    预置因子（source=preset）可通过 status=false 停用"""
    factor = await FactorService.update(db, factor_id, req)
    await db.commit()
    return response_base.success(data=FactorItem.model_validate(factor), msg="更新成功")


@factor_router.delete(
    "/{factor_id}",
    response_model=ResponseModel,
    summary="删除因子（软删除；预置因子不可删除，只能停用）",
    dependencies=[Depends(require_permission("strategy:manage"))],
)
async def delete_factor(
    factor_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """软删除因子；预置因子（source=preset）拒绝删除，请改用更新接口停用"""
    await FactorService.delete(db, factor_id)
    await db.commit()
    return response_base.success(msg="删除成功")
