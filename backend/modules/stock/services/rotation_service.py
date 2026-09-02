#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
板块轮动分析服务：成分股快照同步 + 板块历史回填 + 轮动指标（读时计算，不入库）

指标口径沿用连板概率模式：同步只落原始快照，阶段/评分/切换信号在查询时
基于近 N 日快照现算，规则透明可回验，算法调整无需回刷历史数据。
"""
import asyncio
import bisect
import logging
import math
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError, CustomErrorCode
from database.models.business.stock_market import (
    BusinessBoardDaily,
    BusinessBoardStockDaily,
    BusinessLimitUpStock,
)
from database.utils.timezone import timezone
from modules.stock.schemas.rotation import (
    RotationBackfillResult,
    RotationOverviewItem,
    RotationOverviewResponse,
    RotationSwitchItem,
    RotationSwitchResponse,
    RotationSwitchStockItem,
    RotationSyncResult,
)
from modules.stock.services import board_fetcher

logger = logging.getLogger(__name__)

# 后台任务强引用，防止 asyncio.Task 被 GC 中断
_BACKGROUND_TASKS: set[asyncio.Task] = set()
_SYNC_LOCK = asyncio.Lock()
_BACKFILL_LOCK = asyncio.Lock()

_INSERT_CHUNK = 500
_LIMIT_UP_WINDOW = 3  # 涨停梯队观察窗口（交易日）


def _chunks(rows: list[dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _f(v) -> float | None:
    """Numeric(Decimal) -> float，None 透传"""
    return float(v) if v is not None else None


def _compound_gain(pcts: list[float | None]) -> float | None:
    """按日涨跌幅复合为区间累计涨幅(%)，缺失日跳过（回填行容错）"""
    vals = [v for v in pcts if v is not None]
    if not vals:
        return None
    prod = 1.0
    for v in vals:
        prod *= 1.0 + v / 100.0
    return round((prod - 1.0) * 100.0, 2)


def _classify_stage(
    change_pct: float | None,
    gain_3d: float | None,
    gain_5d: float | None,
    gain_10d: float | None,
    rank: int | None,
    rank_change: int | None,
) -> str:
    """轮动阶段判定（顺序短路：退潮 > 高潮 > 发酵 > 启动 > 蓄势）"""
    if gain_3d is not None and gain_3d <= -1:
        return "ebb"
    if (
        change_pct is not None and change_pct >= 3
        and ((gain_5d is not None and gain_5d >= 8) or (rank is not None and rank <= 5))
    ):
        return "climax"
    if (
        rank is not None and rank <= 15
        and change_pct is not None and change_pct > 0
        and (gain_5d is None or gain_5d >= 3)
    ):
        return "ferment"
    if (
        (rank_change is not None and rank_change >= 10 and (gain_10d is None or gain_10d < 5))
        or (
            change_pct is not None and change_pct >= 1.5
            and gain_10d is not None and gain_10d <= 3
            and rank is not None and rank <= 30
        )
    ):
        return "start"
    return "observe"


def _tomorrow_score(
    position_pct: float | None,
    rank_change: int | None,
    inflow_days: int,
    limit_up_count: int,
    volume_ratio: float | None,
    stage: str,
) -> int:
    """明日轮动候选评分：基准 50，因子加减后收敛到 0-100"""
    score = 50
    if position_pct is not None:
        if position_pct <= 0.3:
            score += 15
        elif position_pct >= 0.85:
            score -= 15
    if rank_change is not None and rank_change >= 10:
        score += 10
    if inflow_days >= 3:
        score += 10
    if limit_up_count >= 3:
        score += 10
    if volume_ratio is not None:
        if 1 <= volume_ratio <= 3:
            score += 5
        elif volume_ratio > 4:
            score -= 5
    if stage == "ebb":
        score -= 20
    return max(0, min(100, score))


def _decide_action(stage: str, score: int, change_pct: float | None) -> str:
    if stage == "ebb":
        return "avoid"
    if score >= 68 and stage in ("ferment", "climax") and (change_pct or 0) > 0:
        return "attack"
    if score >= 55 and stage in ("start", "observe"):
        return "ambush"
    return "watch"


def _pick_position_key(stocks: list) -> str:
    """成分股位置分层键：按 80% 覆盖率优先取近10日/近5日涨幅，兜底当日涨幅"""
    n = len(stocks)
    for field in ("gain_10d", "gain_5d"):
        covered = sum(1 for s in stocks if getattr(s, field) is not None)
        if n and covered / n >= 0.8:
            return field
    return "change_pct"


def _build_switch_item(board: BusinessBoardDaily, stocks: list) -> RotationSwitchItem:
    position_key = _pick_position_key(stocks)
    positioned = [
        (s, float(pos))
        for s in stocks
        if (pos := getattr(s, position_key)) is not None
    ]
    n = len(positioned)
    base = dict(
        board_type=board.board_type,
        board_code=board.board_code,
        board_name=board.board_name,
        change_pct=_f(board.change_pct),
        position_key=position_key,
    )
    if n < 10:
        return RotationSwitchItem(signal="unknown", **base)

    positioned.sort(key=lambda t: t[1], reverse=True)
    k = max(3, math.ceil(n * 0.2))
    if 2 * k > n:
        k = n // 2
    high, low = positioned[:k], positioned[-k:]

    def _avg(group) -> float | None:
        vals = [float(s.change_pct) for s, _ in group if s.change_pct is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    high_avg, low_avg = _avg(high), _avg(low)
    if high_avg is None or low_avg is None:
        signal = "unknown"
    elif (high_avg - low_avg <= -1) or (high_avg < 0 and low_avg >= 1):
        signal = "switching"
    elif high_avg > 1 and low_avg > 1:
        signal = "resonance"
    else:
        signal = "split"

    def _stock_item(s, pos: float):
        return RotationSwitchStockItem(
            stock_code=s.stock_code,
            stock_name=s.stock_name,
            price=_f(s.price),
            change_pct=_f(s.change_pct),
            amount=_f(s.amount),
            position_gain=round(pos, 2),
        )

    high_laggards = [
        _stock_item(s, p) for s, p in sorted(
            high,
            key=lambda t: (t[0].change_pct is None,
                           float(t[0].change_pct) if t[0].change_pct is not None else 0),
        )[:5]
    ]
    low_starters = [
        _stock_item(s, p) for s, p in sorted(
            low,
            key=lambda t: (t[0].change_pct is None,
                           -(float(t[0].change_pct) if t[0].change_pct is not None else 0)),
        )[:5]
    ]
    return RotationSwitchItem(
        signal=signal,
        high_avg_pct=high_avg,
        low_avg_pct=low_avg,
        high_laggards=high_laggards,
        low_starters=low_starters,
        **base,
    )


class RotationService:
    """板块轮动分析服务"""

    CONCEPT_SNAPSHOT_TOP = 30

    # ---------------------------------------------------------------- sync --
    @staticmethod
    async def sync_board_stocks(db: AsyncSession, concept_top: int | None = None) -> dict:
        """抓取活跃板块全部成分股，写入当日快照

        板块选样：行业全量 + 概念当日涨幅前 N（控制请求量，规避 push2 限流）。
        写入采用每板块类型先删当日再插入，防止换源重同步残留混杂数据。
        """
        if _SYNC_LOCK.locked():
            raise CustomError(
                error=CustomErrorCode.ROTATION_SYNC_RUNNING,
                msg="板块成分股同步正在进行中，请稍后再试",
            )
        async with _SYNC_LOCK:
            concept_top = concept_top or RotationService.CONCEPT_SNAPSHOT_TOP
            boards: list[dict] = []
            for bt in ("industry", "concept"):
                latest_date = (await db.execute(
                    select(BusinessBoardDaily.record_date)
                    .where(
                        BusinessBoardDaily.board_type == bt,
                        BusinessBoardDaily.deleted_at.is_(None),
                    )
                    .distinct()
                    .order_by(BusinessBoardDaily.record_date.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if not latest_date:
                    continue
                q = select(BusinessBoardDaily.board_code, BusinessBoardDaily.board_name).where(
                    BusinessBoardDaily.board_type == bt,
                    BusinessBoardDaily.record_date == latest_date,
                    BusinessBoardDaily.deleted_at.is_(None),
                )
                if bt == "concept":
                    q = q.order_by(
                        BusinessBoardDaily.change_pct.desc().nullslast()
                    ).limit(concept_top)
                res = await db.execute(q)
                boards.extend(
                    {"board_type": bt, "board_code": code, "board_name": name}
                    for code, name in res.all()
                )
            if not boards:
                return RotationSyncResult(
                    boards=0, saved_boards=0, stocks=0, failed_boards=0, snapshot_date=None,
                ).model_dump()

            today = timezone.now().date()
            fetched = await board_fetcher.fetch_boards_constituents_batch(boards)
            saved_boards = 0
            rows_by_type: dict[str, list[dict]] = {}
            for board, stocks in fetched:
                if not stocks:
                    continue
                saved_boards += 1
                seen: set[str] = set()
                for s in stocks:
                    if s["stock_code"] in seen:
                        # 分页拉取行情实时变动可能跨页重复，同批重复键会让插入报错
                        continue
                    seen.add(s["stock_code"])
                    rows_by_type.setdefault(board["board_type"], []).append({
                        "record_date": today,
                        "board_type": board["board_type"],
                        "board_code": board["board_code"],
                        "board_name": board["board_name"],
                        "stock_code": s["stock_code"],
                        "stock_name": s["stock_name"],
                        "price": s.get("price"),
                        "change_pct": s.get("change_pct"),
                        "amount": s.get("amount"),
                        "turnover_rate": s.get("turnover_rate"),
                        "gain_5d": s.get("gain_5d"),
                        "gain_10d": s.get("gain_10d"),
                        "created_at": timezone.now(),
                    })

            total = 0
            for bt, rows in rows_by_type.items():
                await db.execute(delete(BusinessBoardStockDaily).where(
                    BusinessBoardStockDaily.record_date == today,
                    BusinessBoardStockDaily.board_type == bt,
                ))
                for chunk in _chunks(rows, _INSERT_CHUNK):
                    await db.execute(insert(BusinessBoardStockDaily).values(chunk))
                total += len(rows)
            await db.commit()

            return RotationSyncResult(
                boards=len(boards),
                saved_boards=saved_boards,
                stocks=total,
                failed_boards=len(boards) - saved_boards,
                snapshot_date=today,
            ).model_dump()

    # ------------------------------------------------------------ backfill --
    @staticmethod
    async def submit_backfill(
        db: AsyncSession, board_type: str = "all", days: int = 60,
    ) -> dict:
        """提交板块历史日K回填（后台任务执行，立即返回）

        business_board_daily 历史由每日同步自然积累，无回填机制；
        轮动指标需要历史纵深，通过 push2his 日K补缺失日期。
        回填行只含行情字段，净流入/涨跌家数等快照字段留空，指标侧 None 容错。
        board_type=all 时行业+概念合并为一个后台任务（单一锁，避免先后两次提交相撞）。
        """
        if _BACKFILL_LOCK.locked():
            raise CustomError(
                error=CustomErrorCode.ROTATION_BACKFILL_RUNNING,
                msg="板块历史回填正在进行中，请稍后再试",
            )
        types = ("industry", "concept") if board_type == "all" else (board_type,)
        boards: list[dict] = []
        for bt in types:
            latest_date = (await db.execute(
                select(BusinessBoardDaily.record_date)
                .where(
                    BusinessBoardDaily.board_type == bt,
                    BusinessBoardDaily.deleted_at.is_(None),
                )
                .distinct()
                .order_by(BusinessBoardDaily.record_date.desc())
                .limit(1)
            )).scalar_one_or_none()
            if not latest_date:
                continue
            res = await db.execute(
                select(BusinessBoardDaily.board_code, BusinessBoardDaily.board_name).where(
                    BusinessBoardDaily.board_type == bt,
                    BusinessBoardDaily.record_date == latest_date,
                    BusinessBoardDaily.deleted_at.is_(None),
                )
            )
            boards.extend(
                {"board_type": bt, "board_code": code, "board_name": name}
                for code, name in res.all()
            )
        if not boards:
            return RotationBackfillResult(
                board_type=board_type, days=days, boards=0, status="no_data",
            ).model_dump()

        await _BACKFILL_LOCK.acquire()
        task = asyncio.create_task(RotationService._run_backfill(board_type, days, boards))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        return RotationBackfillResult(
            board_type=board_type, days=days, boards=len(boards), status="submitted",
        ).model_dump()

    @staticmethod
    async def _run_backfill(board_type: str, days: int, boards: list[dict]) -> None:
        from database.db_manager import get_session

        # 日K的当日bar在盘中为半日数据，且每日板块同步会在收盘后写入正式快照，
        # 回填只补历史缺失日期，避免当日行被盘中数据污染
        today = timezone.now().date()
        try:
            async for db in get_session():
                results = await board_fetcher.fetch_boards_history_batch(boards, days=days)
                inserted = 0
                for board, klines in results:
                    if not klines:
                        continue
                    rows = [{
                        "record_date": date.fromisoformat(k["date"]),
                        "board_type": board.get("board_type") or board_type,
                        "board_code": board["board_code"],
                        "board_name": board["board_name"],
                        "change_pct": k.get("change_pct"),
                        "turnover": k.get("turnover"),
                        "volume": k.get("volume"),
                        "turnover_rate": k.get("turnover_rate"),
                        "created_at": timezone.now(),
                    } for k in klines if date.fromisoformat(k["date"]) < today]
                    try:
                        for chunk in _chunks(rows, _INSERT_CHUNK):
                            stmt = insert(BusinessBoardDaily).values(chunk).on_conflict_do_nothing(
                                index_elements=["record_date", "board_type", "board_code"],
                            )
                            r = await db.execute(stmt)
                            inserted += r.rowcount or 0
                        await db.commit()
                    except Exception as e:  # noqa: BLE001
                        await db.rollback()
                        logger.warning(
                            "板块历史回填单板块失败(%s %s): %s",
                            board["board_code"], board["board_name"], e,
                        )
                logger.info(
                    "板块历史回填完成(%s): 板块 %d 个，新增 %d 行",
                    board_type, len(boards), inserted,
                )
        except Exception as e:  # noqa: BLE001
            logger.error("板块历史回填任务异常(%s): %s", board_type, e)
        finally:
            _BACKFILL_LOCK.release()

    # ------------------------------------------------------------- overview --
    @staticmethod
    async def get_overview(
        db: AsyncSession, board_type: str = "industry", days: int = 10,
    ) -> dict:
        """近期轮动板块总览：近 N 日快照现算阶段/评分/操作建议"""
        dates = list((await db.execute(
            select(BusinessBoardDaily.record_date)
            .where(
                BusinessBoardDaily.board_type == board_type,
                BusinessBoardDaily.deleted_at.is_(None),
            )
            .distinct()
            .order_by(BusinessBoardDaily.record_date.desc())
            .limit(days)
        )).scalars().all())
        if not dates:
            return RotationOverviewResponse(
                snapshot_date=None, history_days=0, items=[],
            ).model_dump()
        snapshot_date = dates[0]

        rows = (await db.execute(
            select(BusinessBoardDaily).where(
                BusinessBoardDaily.board_type == board_type,
                BusinessBoardDaily.record_date.in_(dates),
                BusinessBoardDaily.deleted_at.is_(None),
            )
        )).scalars().all()
        series: dict[str, dict[date, BusinessBoardDaily]] = {}
        for row in rows:
            series.setdefault(row.board_code, {})[row.record_date] = row

        # 各交易日涨幅排名（1=最强），供排名跃升因子与阶段判定使用
        by_date: dict[date, dict[str, float]] = {}
        for code, day_map in series.items():
            for d, row in day_map.items():
                if row.change_pct is not None:
                    by_date.setdefault(d, {})[code] = float(row.change_pct)

        def _rank_map(d: date | None) -> dict[str, int]:
            if d is None or d not in by_date:
                return {}
            ranked = sorted(by_date[d].items(), key=lambda kv: kv[1], reverse=True)
            return {code: i + 1 for i, (code, _) in enumerate(ranked)}

        rank_now = _rank_map(snapshot_date)
        rank_5d_ago = _rank_map(dates[4]) if len(dates) >= 5 else {}

        # 板块自身近10日累计涨幅分布，用于位置百分位（低=低位）
        gain10_map: dict[str, float] = {}
        for code, day_map in series.items():
            if snapshot_date in day_map:
                g = _compound_gain([
                    _f(day_map[d].change_pct) if d in day_map else None
                    for d in dates[:10]
                ])
                if g is not None:
                    gain10_map[code] = g
        g10_vals = sorted(gain10_map.values())

        # 近3日涨停梯队（涨停池 industry 字段按板块名匹配，概念板块通常无命中）
        lu_by_industry: dict[str, dict] = {}
        lu_rows = (await db.execute(
            select(
                BusinessLimitUpStock.industry,
                BusinessLimitUpStock.stock_code,
                BusinessLimitUpStock.consecutive_limit_up,
            ).where(
                BusinessLimitUpStock.record_date.in_(dates[:_LIMIT_UP_WINDOW]),
                BusinessLimitUpStock.deleted_at.is_(None),
            )
        )).all()
        for industry, code, cons in lu_rows:
            if not industry:
                continue
            g = lu_by_industry.setdefault(industry, {"codes": set(), "max_cons": 0})
            g["codes"].add(code)
            if cons and int(cons) > g["max_cons"]:
                g["max_cons"] = int(cons)

        items: list[RotationOverviewItem] = []
        for code, day_map in series.items():
            if snapshot_date not in day_map:
                continue
            today_row = day_map[snapshot_date]
            change_pct = _f(today_row.change_pct)

            gain_3d = _compound_gain([_f(day_map[d].change_pct) if d in day_map else None for d in dates[:3]])
            gain_5d = _compound_gain([_f(day_map[d].change_pct) if d in day_map else None for d in dates[:5]])
            gain_10d = gain10_map.get(code)

            rank = rank_now.get(code)
            rank_prev = rank_5d_ago.get(code)
            rank_change = (rank_prev - rank) if (rank is not None and rank_prev is not None) else None

            prev_turnovers = [
                _f(day_map[d].turnover) for d in dates[1:6] if d in day_map
            ]
            prev_turnovers = [v for v in prev_turnovers if v is not None]
            today_turnover = _f(today_row.turnover)
            volume_ratio = None
            if today_turnover is not None and len(prev_turnovers) >= 3:
                mean_v = sum(prev_turnovers) / len(prev_turnovers)
                if mean_v > 0:
                    volume_ratio = round(today_turnover / mean_v, 2)

            inflow_days = 0
            for d in dates:
                if d not in day_map:
                    break
                v = _f(day_map[d].net_inflow)
                if v is not None and v > 0:
                    inflow_days += 1
                else:
                    break

            lu = lu_by_industry.get(today_row.board_name) or {}
            limit_up_count = len(lu.get("codes", ()))
            max_consecutive = lu.get("max_cons", 0)

            position_pct = None
            if code in gain10_map and len(g10_vals) >= 5:
                position_pct = bisect.bisect_left(g10_vals, gain10_map[code]) / len(g10_vals)

            stage = _classify_stage(change_pct, gain_3d, gain_5d, gain_10d, rank, rank_change)
            score = _tomorrow_score(
                position_pct, rank_change, inflow_days, limit_up_count, volume_ratio, stage,
            )
            action = _decide_action(stage, score, change_pct)

            items.append(RotationOverviewItem(
                board_type=today_row.board_type,
                board_code=code,
                board_name=today_row.board_name,
                change_pct=change_pct,
                gain_3d=gain_3d,
                gain_5d=gain_5d,
                gain_10d=gain_10d,
                rank=rank,
                rank_change=rank_change,
                volume_ratio=volume_ratio,
                inflow_days=inflow_days,
                limit_up_count=limit_up_count,
                max_consecutive=max_consecutive,
                stage=stage,
                tomorrow_score=score,
                action=action,
            ))

        items.sort(key=lambda x: (
            -x.tomorrow_score,
            x.change_pct is None,
            -(x.change_pct or 0),
        ))
        return RotationOverviewResponse(
            snapshot_date=snapshot_date,
            history_days=len(dates),
            items=items,
        ).model_dump()

    # -------------------------------------------------------------- switch --
    @staticmethod
    async def get_switch_signals(
        db: AsyncSession, board_type: str = "industry", top_n: int = 15,
    ) -> dict:
        """板块内高低切换信号：当日涨幅榜前 N 板块的成分股位置分层"""
        board_date = (await db.execute(
            select(BusinessBoardDaily.record_date)
            .where(
                BusinessBoardDaily.board_type == board_type,
                BusinessBoardDaily.deleted_at.is_(None),
            )
            .distinct()
            .order_by(BusinessBoardDaily.record_date.desc())
            .limit(1)
        )).scalar_one_or_none()
        if not board_date:
            return RotationSwitchResponse(snapshot_date=None, items=[]).model_dump()

        top_boards = (await db.execute(
            select(BusinessBoardDaily).where(
                BusinessBoardDaily.board_type == board_type,
                BusinessBoardDaily.record_date == board_date,
                BusinessBoardDaily.change_pct.is_not(None),
                BusinessBoardDaily.deleted_at.is_(None),
            ).order_by(BusinessBoardDaily.change_pct.desc()).limit(top_n)
        )).scalars().all()
        if not top_boards:
            return RotationSwitchResponse(snapshot_date=None, items=[]).model_dump()

        stock_date = (await db.execute(
            select(BusinessBoardStockDaily.record_date)
            .where(
                BusinessBoardStockDaily.board_type == board_type,
                BusinessBoardStockDaily.deleted_at.is_(None),
            )
            .distinct()
            .order_by(BusinessBoardStockDaily.record_date.desc())
            .limit(1)
        )).scalar_one_or_none()

        items = []
        if stock_date:
            stocks_by_board: dict[str, list] = {}
            stock_rows = (await db.execute(
                select(BusinessBoardStockDaily).where(
                    BusinessBoardStockDaily.board_type == board_type,
                    BusinessBoardStockDaily.record_date == stock_date,
                    BusinessBoardStockDaily.board_code.in_(
                        [b.board_code for b in top_boards],
                    ),
                    BusinessBoardStockDaily.deleted_at.is_(None),
                )
            )).scalars().all()
            for s in stock_rows:
                stocks_by_board.setdefault(s.board_code, []).append(s)
            items = [_build_switch_item(b, stocks_by_board.get(b.board_code, []))
                     for b in top_boards]
        else:
            from modules.stock.schemas.rotation import RotationSwitchItem
            items = [
                RotationSwitchItem(
                    board_type=b.board_type,
                    board_code=b.board_code,
                    board_name=b.board_name,
                    change_pct=_f(b.change_pct),
                    signal="unknown",
                    position_key="change_pct",
                )
                for b in top_boards
            ]
        return RotationSwitchResponse(snapshot_date=stock_date, items=items).model_dump()
