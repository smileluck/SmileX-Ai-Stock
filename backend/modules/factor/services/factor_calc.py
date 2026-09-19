#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
因子计算与选股服务

行情复用 backtest 模块的双源抓取（fetch_market_data，akshare 主源、baostock 降级），
计算统一走 formula.calc_factor_values（白名单 DSL 求值器）。
选股为多条件 AND，top_n 表示按因子值降序取前 N 名；不支持全市场选股。
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import RequestError
from database.models.business.strategy import BusinessStrategySignal
from database.utils.timezone import timezone
from modules.backtest.services.market_data import fetch_market_data, is_supported_stock
from modules.factor.schemas.factor import (
    FactorCalcRequest,
    FactorScreenRequest,
    MAX_UNIVERSE_SIZE,
    SavePoolRequest,
)
from modules.factor.services.factor_service import FactorService
from modules.factor.services.formula import calc_factor_values
from modules.strategy.services.strategy_service import StrategyService

logger = logging.getLogger(__name__)


async def _fetch_universe_bars(
    codes: list[str], end_date: str | None, lookback: int
) -> tuple[dict[str, list[dict]], str, list[str]]:
    """抓取 universe 行情并截取到目标日末 lookback 条。

    Returns:
        (bars_by_code, target_day, warnings)；target_day 为 ≤end_date 的最后一个交易日
    """
    end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else timezone.now().date()
    start = end - timedelta(days=lookback * 2)

    warnings: list[str] = []
    supported: list[str] = []
    for code in dict.fromkeys(codes):  # 去重保序
        if is_supported_stock(code):
            supported.append(code)
        else:
            warnings.append(f"股票 [{code}] 暂不支持（北交所等），已跳过")
    if len(supported) > MAX_UNIVERSE_SIZE:
        raise RequestError(msg=f"股票池大小超过上限 {MAX_UNIVERSE_SIZE}")
    if not supported:
        raise RequestError(msg="股票池为空或不包含可支持的 A 股代码")

    data = await fetch_market_data(supported, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    trading_days = [d for d in data["trading_days"] if d <= end.strftime("%Y-%m-%d")]
    if not trading_days:
        raise RequestError(msg=f"截至 {end} 无可用交易日，无法计算因子")
    target_day = trading_days[-1]

    for code in data["failed_codes"]:
        warnings.append(f"股票 [{code}] 行情抓取失败，已跳过")

    bars_by_code: dict[str, list[dict]] = {}
    for code, bars in data["bars"].items():
        trimmed = [b for b in bars if b["date"] <= target_day][-lookback:]
        if trimmed:
            bars_by_code[code] = trimmed
        else:
            warnings.append(f"股票 [{code}] 在目标日 {target_day} 前无行情，已跳过")
    return bars_by_code, target_day, warnings


async def _latest_stock_names(db: AsyncSession, codes: list[str]) -> dict[str, str]:
    """best-effort 股票简称：取各代码最近一条 AI 信号的 stock_name，无信号则为空串"""
    if not codes:
        return {}
    result = await db.execute(
        select(BusinessStrategySignal.stock_code, BusinessStrategySignal.stock_name)
        .where(
            BusinessStrategySignal.stock_code.in_(codes),
            BusinessStrategySignal.deleted_at.is_(None),
        )
        .order_by(BusinessStrategySignal.created_at.desc(), BusinessStrategySignal.id.desc())
    )
    names: dict[str, str] = {}
    for code, name in result.all():
        if code not in names:
            names[code] = name
    return names


class FactorCalcService:
    """因子计算与选股服务类"""

    # ------------------------------------------------------------------
    # 因子计算
    # ------------------------------------------------------------------
    @staticmethod
    async def calc(db: AsyncSession, req: FactorCalcRequest) -> dict:
        """对给定股票池计算目标日因子值，返回 {factor_id, factor_code, end_date, values, warnings}"""
        factor = await FactorService.get_by_id(db, req.factor_id)
        bars_by_code, target_day, warnings = await _fetch_universe_bars(
            req.codes, req.end_date, req.lookback
        )
        values, calc_warnings = calc_factor_values(factor.formula, bars_by_code)
        warnings.extend(calc_warnings)
        return {
            "factor_id": factor.id,
            "factor_code": factor.code,
            "end_date": target_day,
            "values": [{"code": code, "value": values[code]} for code in sorted(values)],
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # 选股器（多条件 AND）
    # ------------------------------------------------------------------
    @staticmethod
    async def screen(db: AsyncSession, req: FactorScreenRequest) -> dict:
        """按条件筛选股票池，返回 {total, end_date, matched, warnings}

        universe 来自 codes 或策略股票池（strategy_id）；条件间为 AND；
        top_n 条件按该因子值降序取前 N 名后与其他条件求交集。
        """
        universe = await FactorCalcService._resolve_universe(db, req)
        bars_by_code, target_day, warnings = await _fetch_universe_bars(
            universe, req.end_date, req.lookback
        )

        # 逐因子计算（同一因子多条件只算一次）
        factor_ids = {c.factor_id for c in req.conditions}
        factors = {fid: await FactorService.get_by_id(db, fid) for fid in factor_ids}
        factor_values: dict[int, dict[str, float]] = {}
        for fid, factor in factors.items():
            values, calc_warnings = calc_factor_values(factor.formula, bars_by_code)
            warnings.extend(calc_warnings)
            factor_values[fid] = values

        matched = set(bars_by_code.keys())
        for cond in req.conditions:
            values = factor_values[cond.factor_id]
            if cond.op == "top_n":
                n = int(cond.value)
                if n < 1 or n != cond.value:
                    raise RequestError(msg=f"top_n 条件的 value 必须为正整数，实际 {cond.value}")
                ranked = sorted(
                    (code for code in matched if values.get(code) is not None),
                    key=lambda c: values[c],
                    reverse=True,
                )
                matched &= set(ranked[:n])
            else:
                matched = {
                    code for code in matched
                    if values.get(code) is not None and _compare(values[code], cond.op, cond.value)
                }
            if not matched:
                break

        ordered = sorted(matched)
        names = await _latest_stock_names(db, ordered)
        matched_items = [
            {
                "code": code,
                "name": names.get(code, ""),
                "factor_values": {
                    factors[fid].code: factor_values[fid].get(code)
                    for fid in (c.factor_id for c in req.conditions)
                },
            }
            for code in ordered
        ]
        return {
            "total": len(matched_items),
            "end_date": target_day,
            "matched": matched_items,
            "warnings": warnings,
        }

    @staticmethod
    async def _resolve_universe(db: AsyncSession, req: FactorScreenRequest) -> list[str]:
        if req.codes:
            return list(dict.fromkeys(req.codes))
        strategy = await StrategyService.get_by_id(db, req.strategy_id)
        codes = (strategy.stock_pool or {}).get("codes") or []
        if not codes:
            raise RequestError(msg=f"策略 [{req.strategy_id}] 的股票池为空")
        return list(dict.fromkeys(codes))

    # ------------------------------------------------------------------
    # 选股结果保存为策略股票池
    # ------------------------------------------------------------------
    @staticmethod
    async def save_pool(db: AsyncSession, req: SavePoolRequest) -> dict:
        """覆盖式保存策略股票池：strategy.stock_pool = {"codes": [...]}"""
        strategy = await StrategyService.get_by_id(db, req.strategy_id)
        codes = list(dict.fromkeys(c.strip() for c in req.codes if c.strip()))
        if len(codes) > MAX_UNIVERSE_SIZE:
            raise RequestError(msg=f"股票池大小超过上限 {MAX_UNIVERSE_SIZE}")
        strategy.stock_pool = {"codes": codes}
        await db.flush()
        logger.info("策略股票池已更新: strategy_id=%s total=%s", strategy.id, len(codes))
        return {"strategy_id": strategy.id, "total": len(codes)}


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    raise RequestError(msg=f"不支持的选股操作符 [{op}]")
