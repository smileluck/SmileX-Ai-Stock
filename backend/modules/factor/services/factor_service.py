#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
因子管理服务：CRUD + 在线导入

因子来源：preset-迁移种子预置（不可删除，只可停用）、imported-在线导入、custom-手工自建。
公式统一经 formula.validate_formula 白名单校验后才允许落库。
"""
import json
import logging

import httpx
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode
from database.models.business.factor import BusinessFactor
from modules.factor.schemas.factor import (
    FactorCreateRequest,
    FactorImportRequest,
    FactorItem,
    FactorUpdateRequest,
)
from modules.factor.services.formula import validate_formula

logger = logging.getLogger(__name__)

# 导入 URL 抓取超时（秒）
_IMPORT_TIMEOUT = 15


class FactorService:
    """因子管理服务类"""

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @staticmethod
    async def get_by_id(db: AsyncSession, factor_id: int) -> BusinessFactor:
        result = await db.execute(
            select(BusinessFactor).where(
                BusinessFactor.id == factor_id,
                BusinessFactor.deleted_at.is_(None),
            )
        )
        factor = result.scalar_one_or_none()
        if not factor:
            raise CustomError(
                error=CustomErrorCode.FACTOR_NOT_FOUND,
                msg=f"因子 [{factor_id}] 不存在",
            )
        return factor

    @staticmethod
    async def get_list(
        db: AsyncSession,
        category: str | None = None,
        source: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FactorItem], int]:
        """分页查询因子列表（按创建时间倒序），返回 (items, total)"""
        conditions = [BusinessFactor.deleted_at.is_(None)]
        if category:
            conditions.append(BusinessFactor.category == category)
        if source:
            conditions.append(BusinessFactor.source == source)
        if keyword:
            like = f"%{keyword}%"
            conditions.append(or_(BusinessFactor.name.like(like), BusinessFactor.code.like(like)))

        count_result = await db.execute(
            select(func.count()).select_from(BusinessFactor).where(*conditions)
        )
        total = count_result.scalar() or 0
        result = await db.execute(
            select(BusinessFactor)
            .where(*conditions)
            .order_by(BusinessFactor.created_at.desc(), BusinessFactor.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [FactorItem.model_validate(row) for row in result.scalars().all()]
        return items, total

    # ------------------------------------------------------------------
    # 创建 / 更新 / 删除
    # ------------------------------------------------------------------
    @staticmethod
    async def _ensure_code_available(db: AsyncSession, code: str) -> None:
        """code 全局唯一（含已软删除记录，DB 层有唯一约束）"""
        result = await db.execute(
            select(BusinessFactor.id).where(BusinessFactor.code == code).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.FACTOR_CODE_CONFLICT,
                msg=f"因子代码 [{code}] 已存在",
            )

    @staticmethod
    async def create(db: AsyncSession, req: FactorCreateRequest) -> BusinessFactor:
        """手工创建因子（source 固定 custom），公式先经白名单校验"""
        validate_formula(req.formula)
        code = req.code.strip()
        await FactorService._ensure_code_available(db, code)
        factor = BusinessFactor(
            name=req.name.strip(),
            code=code,
            category=req.category,
            formula=req.formula.strip(),
            description=req.description,
            source="custom",
            source_url=req.source_url,
            params=req.params,
            status=req.status,
        )
        db.add(factor)
        await db.flush()
        return factor

    @staticmethod
    async def update(db: AsyncSession, factor_id: int, req: FactorUpdateRequest) -> BusinessFactor:
        """按传入字段更新因子；code/source 不可改；公式变更需重新通过白名单校验"""
        factor = await FactorService.get_by_id(db, factor_id)
        if req.formula is not None:
            validate_formula(req.formula)
            factor.formula = req.formula.strip()
        if req.name is not None:
            factor.name = req.name.strip()
        if req.category is not None:
            factor.category = req.category
        if req.description is not None:
            factor.description = req.description
        if req.source_url is not None:
            factor.source_url = req.source_url
        if req.params is not None:
            factor.params = req.params
        if req.status is not None:
            factor.status = req.status
        await db.flush()
        return factor

    @staticmethod
    async def delete(db: AsyncSession, factor_id: int) -> None:
        """软删除因子；预置因子（source=preset）不可删除，只能通过更新 status 停用"""
        factor = await FactorService.get_by_id(db, factor_id)
        if factor.source == "preset":
            raise CustomError(
                error=CustomErrorCode.FACTOR_PRESET_DELETE_FORBIDDEN,
                msg=f"预置因子 [{factor.code}] 不可删除，只能停用",
            )
        factor.soft_delete()
        await db.flush()

    # ------------------------------------------------------------------
    # 在线导入
    # ------------------------------------------------------------------
    @staticmethod
    async def import_factors(db: AsyncSession, req: FactorImportRequest) -> dict:
        """从 URL 或粘贴的 JSON 导入因子。

        JSON 格式：[{name, code, category?, formula, description?, source_url?}]（或单个对象）。
        逐条校验公式与 code 唯一性（含本批次内重复），非法/冲突条目跳过并记入 errors；
        整体获取/解析失败抛 FACTOR_IMPORT_FAILED。
        """
        raw = await FactorService._load_import_payload(req)
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            raise CustomError(
                error=CustomErrorCode.FACTOR_IMPORT_FAILED,
                msg="因子 JSON 必须为对象数组（或单个对象）",
            )

        imported, skipped, errors = 0, 0, []
        batch_codes: set[str] = set()
        for idx, item in enumerate(raw):
            label = f"第 {idx + 1} 条"
            try:
                factor = await FactorService._build_imported_factor(db, item, batch_codes, req.url)
            except CustomError as e:
                skipped += 1
                errors.append(f"{label}：{e.msg or e.default_msg_key}")
                continue
            batch_codes.add(factor.code)
            db.add(factor)
            imported += 1
        if imported:
            await db.flush()
        logger.info("因子导入完成: imported=%s skipped=%s", imported, skipped)
        return {"imported": imported, "skipped": skipped, "errors": errors}

    @staticmethod
    async def _load_import_payload(req: FactorImportRequest):
        if req.content:
            try:
                return json.loads(req.content)
            except json.JSONDecodeError as e:
                raise CustomError(
                    error=CustomErrorCode.FACTOR_IMPORT_FAILED,
                    msg=f"因子 JSON 解析失败：{e}",
                )
        try:
            async with httpx.AsyncClient(timeout=_IMPORT_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(req.url)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as e:
            raise CustomError(
                error=CustomErrorCode.FACTOR_IMPORT_FAILED,
                msg=f"从 URL 获取因子 JSON 失败：{e}",
            )

    @staticmethod
    async def _build_imported_factor(
        db: AsyncSession, item, batch_codes: set[str], request_url: str | None
    ) -> BusinessFactor:
        """校验并构造单条导入因子（不落库）"""
        if not isinstance(item, dict):
            raise CustomError(error=CustomErrorCode.FACTOR_IMPORT_FAILED, msg="条目必须为 JSON 对象")
        name = str(item.get("name") or "").strip()
        code = str(item.get("code") or "").strip()
        formula = str(item.get("formula") or "").strip()
        if not name or not code or not formula:
            raise CustomError(
                error=CustomErrorCode.FACTOR_IMPORT_FAILED,
                msg="条目缺少必填字段 name/code/formula",
            )
        if len(code) > 50 or len(name) > 100:
            raise CustomError(
                error=CustomErrorCode.FACTOR_IMPORT_FAILED,
                msg=f"字段超长（name≤100, code≤50）：{code or name}",
            )
        # 公式白名单校验（非法抛 FACTOR_FORMULA_INVALID，由上层记入 errors）
        validate_formula(formula)
        if code in batch_codes:
            raise CustomError(
                error=CustomErrorCode.FACTOR_CODE_CONFLICT,
                msg=f"因子代码 [{code}] 在本批次中重复",
            )
        result = await db.execute(
            select(BusinessFactor.id).where(BusinessFactor.code == code).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.FACTOR_CODE_CONFLICT,
                msg=f"因子代码 [{code}] 已存在，跳过",
            )
        category = str(item.get("category") or "imported").strip()[:30]
        description = item.get("description")
        source_url = item.get("source_url") or request_url
        return BusinessFactor(
            name=name,
            code=code,
            category=category,
            formula=formula,
            description=str(description)[:500] if description else None,
            source="imported",
            source_url=str(source_url)[:500] if source_url else None,
            status=True,
        )
