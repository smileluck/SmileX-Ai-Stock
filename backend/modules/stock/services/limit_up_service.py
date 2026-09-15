#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
涨停/炸板股池服务：同步入库 + 查询
"""
import logging
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.business.stock_market import BusinessLimitUpStock
from database.utils.timezone import timezone
from modules.stock.schemas.limit_up import (
    ContinuationFactor,
    LimitUpStockItem,
    LimitUpStats,
)
from modules.stock.services import limit_up_fetcher

logger = logging.getLogger(__name__)


def _parse_seal_time(value: str | None) -> int | None:
    """封板时间转当日分钟数，兼容 HHMMSS（东财原始）与 HH:MM:SS 两种格式"""
    if not value:
        return None
    s = str(value).replace(":", "").strip()
    if not s.isdigit() or len(s) < 4:
        return None
    hour, minute = int(s[:2]), int(s[2:4])
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def calc_continuation(item: LimitUpStockItem) -> tuple[int, list[ContinuationFactor]]:
    """连板概率启发式评分（0-100，截断到 5..95）：基于封板质量的规则评分，非模型预测

    因子与权重（理论满分 113）：
    - 连板高度（20-35）：2-3 板资金合力最强，高位板接力分歧加大
    - 封成比 = 封单资金/成交额（2-30）：封单相对当日抛压的强度，最核心因子
    - 炸板次数（0-20）：反复开板说明多空分歧严重
    - 首封时间（2-20）：封板越早意愿越坚决，09:25 集合竞价封死最强
    - 换手率（-6~8）：温和换手延续性好，天量换手分歧大
    """
    factors: list[ContinuationFactor] = []
    score = 0

    consec = item.consecutive_limit_up or 1
    score += {1: 20, 2: 30, 3: 35, 4: 32}.get(consec, 28)
    factors.append(ContinuationFactor(type="consecutive", value=float(consec)))

    seal_ratio = None
    if item.seal_amount is not None and item.turnover:
        seal_ratio = item.seal_amount / item.turnover
        score += (
            30 if seal_ratio >= 1.0
            else 26 if seal_ratio >= 0.6
            else 20 if seal_ratio >= 0.3
            else 14 if seal_ratio >= 0.15
            else 8 if seal_ratio >= 0.05
            else 2
        )
    else:
        score += 12
    factors.append(
        ContinuationFactor(
            type="seal_ratio", value=round(seal_ratio, 2) if seal_ratio is not None else None
        )
    )

    breaks = item.break_count
    if breaks is None:
        score += 10
    else:
        score += 20 if breaks == 0 else 10 if breaks == 1 else 4 if breaks == 2 else 0
    factors.append(
        ContinuationFactor(type="break_count", value=float(breaks) if breaks is not None else None)
    )

    minutes = _parse_seal_time(item.first_limit_up_time)
    if minutes is None:
        score += 10
    else:
        score += (
            20 if minutes <= 9 * 60 + 31
            else 16 if minutes <= 10 * 60
            else 12 if minutes <= 10 * 60 + 30
            else 8 if minutes <= 13 * 60 + 30
            else 4 if minutes <= 14 * 60 + 30
            else 2
        )
    factors.append(ContinuationFactor(type="first_seal", value=item.first_limit_up_time))

    rate = item.turnover_rate
    if rate is not None:
        score += 8 if rate <= 10 else 5 if rate <= 20 else 0 if rate <= 30 else -6
    factors.append(ContinuationFactor(type="turnover_rate", value=rate))

    return max(5, min(95, score)), factors


class LimitUpService:
    """涨停/炸板股池服务"""

    @staticmethod
    async def sync_all(db: AsyncSession) -> dict:
        """抓取当日涨停股池 + 炸板股池并写入快照"""
        today = timezone.now().date()
        trade_date = today.strftime("%Y%m%d")
        raw_items = await limit_up_fetcher.fetch_limit_up_pool(trade_date)

        # 炸板池失败不阻塞涨停池入库（接口仅支持最近 30 个交易日）
        try:
            broken_items = await limit_up_fetcher.fetch_broken_pool(trade_date)
        except Exception as e:
            logger.warning("炸板股池抓取失败(date=%s)，跳过: %s", trade_date, e)
            broken_items = []

        rows = []
        for it in raw_items:
            rows.append({
                "record_date": today,
                "stock_code": it["stock_code"],
                "stock_name": it["stock_name"],
                "pool_type": "limit_up",
                "market_board": it["market_board"],
                "latest_price": it.get("latest_price"),
                "change_pct": it.get("change_pct"),
                "turnover_rate": it.get("turnover_rate"),
                "turnover": it.get("turnover"),
                "amplitude": it.get("amplitude"),
                "seal_amount": it.get("seal_amount"),
                "first_limit_up_time": it.get("first_limit_up_time"),
                "last_limit_up_time": it.get("last_limit_up_time"),
                "break_count": it.get("break_count"),
                "consecutive_limit_up": it.get("consecutive_limit_up"),
                "industry": it.get("industry"),
                "limit_up_reason": it.get("limit_up_reason"),
                "created_at": timezone.now(),
            })
        for it in broken_items:
            rows.append({
                "record_date": today,
                "stock_code": it["stock_code"],
                "stock_name": it["stock_name"],
                "pool_type": "broken",
                "market_board": it["market_board"],
                "latest_price": it.get("latest_price"),
                "change_pct": it.get("change_pct"),
                "turnover_rate": it.get("turnover_rate"),
                "turnover": it.get("turnover"),
                "amplitude": it.get("amplitude"),
                "seal_amount": it.get("seal_amount"),
                "first_limit_up_time": it.get("first_limit_up_time"),
                "last_limit_up_time": it.get("last_limit_up_time"),
                "break_count": it.get("break_count"),
                "consecutive_limit_up": it.get("consecutive_limit_up"),
                "industry": it.get("industry"),
                "limit_up_reason": it.get("limit_up_reason"),
                "created_at": timezone.now(),
            })
        broken_count = len(broken_items)
        if not rows:
            return {"fetched": 0, "saved": 0, "broken": 0}

        stmt = insert(BusinessLimitUpStock).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["record_date", "stock_code", "pool_type"],
            set_={
                "stock_name": stmt.excluded.stock_name,
                "market_board": stmt.excluded.market_board,
                "latest_price": stmt.excluded.latest_price,
                "change_pct": stmt.excluded.change_pct,
                "turnover_rate": stmt.excluded.turnover_rate,
                "turnover": stmt.excluded.turnover,
                "amplitude": stmt.excluded.amplitude,
                "seal_amount": stmt.excluded.seal_amount,
                "first_limit_up_time": stmt.excluded.first_limit_up_time,
                "last_limit_up_time": stmt.excluded.last_limit_up_time,
                "break_count": stmt.excluded.break_count,
                "consecutive_limit_up": stmt.excluded.consecutive_limit_up,
                "industry": stmt.excluded.industry,
                "limit_up_reason": stmt.excluded.limit_up_reason,
                "updated_at": timezone.now(),
            },
        )
        result = await db.execute(stmt)
        await db.commit()

        return {
            "fetched": len(raw_items),
            "saved": result.rowcount or 0,
            "broken": broken_count,
        }

    @staticmethod
    async def _resolve_date(db: AsyncSession, record_date: str | None) -> date | None:
        if record_date:
            return date.fromisoformat(record_date)
        latest = await db.execute(
            select(BusinessLimitUpStock.record_date)
            .where(BusinessLimitUpStock.deleted_at.is_(None))
            .distinct()
            .order_by(BusinessLimitUpStock.record_date.desc())
            .limit(1)
        )
        return latest.scalar_one_or_none()

    @staticmethod
    async def get_list(
        db: AsyncSession,
        record_date: str | None = None,
        market_board: str = "all",
        pool_type: str = "all",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[LimitUpStockItem], int]:
        """获取涨停/炸板股列表（分页），返回 (items, total)"""
        target_date = await LimitUpService._resolve_date(db, record_date)
        if not target_date:
            return [], 0

        base = select(BusinessLimitUpStock).where(
            BusinessLimitUpStock.record_date == target_date,
            BusinessLimitUpStock.deleted_at.is_(None),
        )
        if market_board != "all":
            base = base.where(BusinessLimitUpStock.market_board == market_board)
        if pool_type != "all":
            base = base.where(BusinessLimitUpStock.pool_type == pool_type)

        # 按连板数降序，其次按成交额降序
        base = base.order_by(
            BusinessLimitUpStock.consecutive_limit_up.desc().nulls_last(),
            BusinessLimitUpStock.turnover.desc().nulls_last(),
        )

        count_q = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_q)).scalar() or 0

        data_q = base.offset(offset).limit(limit)
        result = await db.execute(data_q)
        items = []
        for row in result.scalars().all():
            item = LimitUpStockItem.model_validate(row)
            # 已炸板个股连板概率无意义，跳过评分
            if item.pool_type != "broken":
                item.continuation_probability, item.continuation_factors = calc_continuation(item)
            items.append(item)
        return items, total

    @staticmethod
    async def get_stats(
        db: AsyncSession, record_date: str | None = None
    ) -> LimitUpStats:
        """获取当日涨停统计（涨停家数口径不变，仅统计封板股；炸板家数单列）"""
        target_date = await LimitUpService._resolve_date(db, record_date)
        if not target_date:
            return LimitUpStats()

        base = select(BusinessLimitUpStock).where(
            BusinessLimitUpStock.record_date == target_date,
            BusinessLimitUpStock.deleted_at.is_(None),
        )

        result = await db.execute(base)
        rows = result.scalars().all()

        stats = LimitUpStats(record_date=target_date)
        board_dist: dict[str, int] = {}
        max_consec = 0
        for row in rows:
            if row.pool_type == "broken":
                stats.broken_count += 1
                continue

            stats.total_count += 1
            board = row.market_board
            if board == "main":
                stats.main_count += 1
            elif board == "chinext":
                stats.chinext_count += 1
            elif board == "star":
                stats.star_count += 1
            elif board == "bse":
                stats.bse_count += 1

            consec = row.consecutive_limit_up or 1
            if consec > max_consec:
                max_consec = consec

            ind = row.industry or "未分类"
            board_dist[ind] = board_dist.get(ind, 0) + 1

        stats.max_consecutive = max_consec
        stats.board_distribution = board_dist
        return stats

    @staticmethod
    async def get_dates(db: AsyncSession) -> list[date]:
        """获取可回看日期列表"""
        result = await db.execute(
            select(BusinessLimitUpStock.record_date)
            .where(BusinessLimitUpStock.deleted_at.is_(None))
            .distinct()
            .order_by(BusinessLimitUpStock.record_date.desc())
        )
        return list(result.scalars().all())
