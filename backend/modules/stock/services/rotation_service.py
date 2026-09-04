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
    RotationThemeItem,
)
from modules.stock.services import board_fetcher

logger = logging.getLogger(__name__)

# 后台任务强引用，防止 asyncio.Task 被 GC 中断
_BACKGROUND_TASKS: set[asyncio.Task] = set()
_SYNC_LOCK = asyncio.Lock()
_BACKFILL_LOCK = asyncio.Lock()

_INSERT_CHUNK = 500
_LIMIT_UP_WINDOW = 3  # 涨停梯队观察窗口（交易日）

# 主题分组：轮动以主题为单位展开（军工/算力AI/医药等），多板块同动=资金集结。
# 板块名按元组顺序做子串匹配，命中任一关键词即归入主题；未命中返回 None。
# 关键词须保持互斥（如军工不含裸"航空"，避免误吸航空机场/航空运输等交运板块）。
THEME_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("军工", ("军工", "国防", "航天", "航空装备", "航空发动机", "通用航空", "大飞机",
              "军民", "兵装", "兵器", "舰船", "船舶", "北斗", "无人机", "卫星", "低空", "航发")),
    ("算力AI", ("算力", "AI", "人工智能", "大模型", "AIGC", "Sora", "GPT", "昇腾", "英伟达",
                "光模块", "CPO", "液冷", "数据中心", "算电", "东数西算", "IT服务", "软件",
                "云计算", "信创", "数据要素", "PCB", "覆铜板", "铜缆", "光通信", "网络安全")),
    ("半导体", ("半导体", "芯片", "集成电路", "晶圆", "光刻", "封测", "存储", "氮化镓",
                "碳化硅", "第三代半导体")),
    ("机器人", ("机器人", "人形", "减速器", "伺服", "执行器", "灵巧手", "空心杯电机",
                "丝杠", "自动化设备", "工业自动化")),
    ("农业牧渔", ("农业", "种植", "种业", "养殖", "饲料", "猪", "鸡", "水产", "渔业", "农机",
                  "动物保健", "兽药", "农药")),
    ("医药医疗", ("医药", "医疗", "药", "疫苗", "医美", "眼科", "牙科", "CXO", "生物", "流感",
                  "脑科学", "脑机", "维生素", "减肥药")),
    ("消费零售", ("白酒", "啤酒", "酒", "食品", "饮料", "乳业", "调味", "零售", "百货", "商贸",
                  "免税", "电商", "纺织", "服装", "鞋", "化妆品", "美容", "个护", "家居", "家电",
                  "宠物", "旅游", "酒店", "餐饮", "景区")),
    ("新能源", ("锂", "光伏", "储能", "风电", "风能", "氢能", "核电", "钠电", "固态电池", "电池",
                "充电", "换电", "新能源")),
    ("汽车", ("汽车", "整车", "零部件", "车联网", "智能驾驶", "自动驾驶", "无人驾驶", "车路云")),
    ("电力公用", ("电力", "电网", "特高压", "虚拟电厂", "电厂", "水电", "火电", "绿电", "燃气",
                  "水务", "环保")),
    ("煤炭石油", ("煤炭", "焦煤", "石油", "油气", "页岩", "油服", "天然气")),
    ("有色贵金属", ("黄金", "白银", "贵金属", "有色", "铜", "铝", "稀土", "磁材", "钨", "钼",
                    "镍", "锡", "锑", "钢铁", "铁矿")),
    ("化工", ("化工", "化学", "化纤", "塑料", "橡胶", "氟", "磷", "尿素", "化肥", "民爆", "钛白",
              "涂料", "染料", "纤维", "玻纤", "碳纤维")),
    ("传媒游戏", ("传媒", "游戏", "影视", "广告", "出版", "广电", "视频", "短剧", "谷子",
                  "数字阅读", "院线")),
    ("金融", ("银行", "证券", "保险", "券商", "多元金融", "信托", "期货", "支付")),
    ("地产基建", ("房地产", "地产", "建筑", "基建", "水泥", "玻璃", "钢结构", "装配式", "城投",
                  "园林")),
    ("交通物流", ("航空机场", "机场", "航运", "港口", "快递", "物流", "铁路", "公路", "高铁",
                  "交通运输", "航空运输")),
    ("通信", ("通信", "5G", "6G", "运营商")),
)


def _board_theme(name: str) -> str | None:
    """板块名 -> 主题（关键词聚合，跨行业/概念口径）"""
    for theme, keywords in THEME_GROUPS:
        if any(k in name for k in keywords):
            return theme
    return None


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
    rank_pct: float | None,
    rank_change: int | None,
    rank_change_3d: int | None,
    inflow_days: int,
) -> str:
    """轮动阶段判定（顺序短路：退潮 > 高潮 > 发酵 > 启动 > 蓄势）

    rank_pct 为当日涨幅榜分位（0=最强），跨行业(~124)/概念(~800)口径统一。
    启动含三种子形态：排名跃升 / 低位当日放量 / 资金潜伏（连续净流入+温和走强
    +整体低位，名次未必靠前，典型提前埋伏形态）。
    """
    if gain_3d is not None and gain_3d <= -1:
        return "ebb"
    if (
        change_pct is not None and change_pct >= 3
        and ((gain_5d is not None and gain_5d >= 8) or (rank_pct is not None and rank_pct <= 0.05))
    ):
        return "climax"
    if (
        rank_pct is not None and rank_pct <= 0.12
        and change_pct is not None and change_pct > 0
        and (gain_5d is None or gain_5d >= 3)
    ):
        return "ferment"
    if (
        (
            (rank_change is not None and rank_change >= 10 and (gain_10d is None or gain_10d < 5))
            or (rank_change_3d is not None and rank_change_3d >= 15
                and (gain_10d is None or gain_10d < 5))
        )
        or (
            change_pct is not None and change_pct >= 1.5
            and gain_10d is not None and gain_10d <= 3
            and rank_pct is not None and rank_pct <= 0.25
        )
        or (
            inflow_days >= 4
            and (gain_5d or 0) >= 3
            and (gain_10d is None or gain_10d <= 6)
            and change_pct is not None and change_pct > -1
            and (rank_pct is None or rank_pct <= 0.65)
        )
    ):
        return "start"
    return "observe"


def _tomorrow_score(f: dict, theme: dict | None) -> int:
    """明日轮动候选评分：基准 50，因子加减后收敛到 0-100

    - 位置：低位(<=30分位)+8，低位且近5日温和走强(>=2%)再+8（提前埋伏形态）；
      高位(>=85分位)-15，高位但量比>=1.2 缩至 -8（强者恒强延续）
    - 排名跃升(5日)：>=30位+10 / >=10位+7 / >=5位+3；近3日累计涨幅<1% 视为微幅
      波动噪声减半（概念池近千板块，小板块名次天然高波动）
    - 资金连续性：净流入连续 >=5日+12 / 4日+9 / 3日+6（连续流入=机构集结）
    - 涨停梯队：近3日 >=3家+10 / 2家+5
    - 量比：1-3 健康放量 +5；>4 过热 -5
    - 阶段：退潮 -20
    - 主题热度：所属主题集结升温（多板块同动且低位）+10，成员净流入占比>=0.55
      再+4；主题高位过热时中高位成员 -5（补涨兑现风险）
    """
    score = 50
    pos, g5 = f.get("position_pct"), f.get("gain_5d")
    if pos is not None:
        if pos <= 0.3:
            score += 8
            if (g5 or 0) >= 2:
                score += 8
        elif pos >= 0.85:
            score -= 8 if (f.get("volume_ratio") or 0) >= 1.2 else 15
    rc = f.get("rank_change")
    if rc is not None and rc >= 5:
        tier = 10 if rc >= 30 else (7 if rc >= 10 else 3)
        if (f.get("gain_3d") or 0) < 1:
            tier //= 2
        score += tier
    inflow = f.get("inflow_days") or 0
    if inflow >= 5:
        score += 12
    elif inflow == 4:
        score += 9
    elif inflow == 3:
        score += 6
    lu = f.get("limit_up_count") or 0
    if lu >= 3:
        # 板块指数当日下跌时的涨停多为龙头独行（分歧结构），梯队确认力度减半
        score += 5 if (f.get("change_pct") or 0) < 0 else 10
    elif lu == 2:
        score += 2 if (f.get("change_pct") or 0) < 0 else 5
    vr = f.get("volume_ratio")
    if vr is not None:
        if 1 <= vr <= 3:
            score += 5
        elif vr > 4:
            score -= 5
    if f.get("stage") == "ebb":
        score -= 20
    t = theme or {}
    if t.get("member_count", 0) >= 3:
        status = t.get("status")
        if status == "gathering":
            score += 10
            if (t.get("inflow_ratio") or 0) >= 0.55:
                score += 4
        elif status == "hot" and (pos is None or pos >= 0.6):
            score -= 5
    return max(0, min(100, round(score)))


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
    def _calc_theme_heat(all_factors: list[dict]) -> list[dict]:
        """主题热度：跨行业+概念因子按主题聚合，热度 = 广度40 + 动量25 + 资金20 + 低位15

        rising_ratio_3d（近3日成员上涨占比）是资金集结的核心信号：单一板块异动
        可能是噪声，同主题多板块齐动大概率是资金进场布局。
        """
        groups: dict[str, list[dict]] = {}
        for fac in all_factors:
            t = fac.get("theme")
            if t:
                groups.setdefault(t, []).append(fac)

        def _avg(vals: list) -> float | None:
            return round(sum(vals) / len(vals), 2) if vals else None

        out: list[dict] = []
        for theme, members in groups.items():
            if len(members) < 2:
                continue
            g3 = [m["gain_3d"] for m in members if m["gain_3d"] is not None]
            g5 = [m["gain_5d"] for m in members if m["gain_5d"] is not None]
            chg = [m["change_pct"] for m in members if m["change_pct"] is not None]
            inflow = [m["net_inflow"] for m in members if m["net_inflow"] is not None]
            pos = [m["position_pct"] for m in members if m["position_pct"] is not None]
            rising_ratio_3d = (
                round(sum(1 for v in g3 if v > 0) / len(g3), 2) if g3 else None
            )
            inflow_ratio = (
                round(sum(1 for v in inflow if v > 0) / len(inflow), 2) if inflow else None
            )
            avg_gain_3d, avg_gain_5d, avg_pos = _avg(g3), _avg(g5), _avg(pos)

            heat = 0.0
            if rising_ratio_3d is not None:
                heat += 40 * rising_ratio_3d
            if avg_gain_5d is not None:
                heat += 25 * min(1.0, max(0.0, avg_gain_5d) / 5)
            if inflow_ratio is not None:
                heat += 20 * inflow_ratio
            if avg_pos is not None:
                heat += 15 * (1 - avg_pos)

            if avg_pos is not None and avg_pos >= 0.8 and (avg_gain_5d or 0) >= 3:
                status = "hot"
            elif (rising_ratio_3d is not None and rising_ratio_3d <= 0.35) or (
                avg_gain_3d is not None and avg_gain_3d <= -1
            ):
                status = "cooling"
            elif (
                (rising_ratio_3d or 0) >= 0.7
                and (avg_pos is None or avg_pos <= 0.5)
                and (avg_gain_5d or 0) >= 1
            ):
                status = "gathering"
            elif (avg_gain_5d or 0) >= 3:
                status = "active"
            else:
                status = "flat"

            out.append({
                "theme": theme,
                "member_count": len(members),
                "avg_change_pct": _avg(chg),
                "avg_gain_3d": avg_gain_3d,
                "avg_gain_5d": avg_gain_5d,
                "rising_ratio_3d": rising_ratio_3d,
                "inflow_ratio": inflow_ratio,
                "avg_position_pct": avg_pos,
                "limit_up_total": sum(m.get("limit_up_count") or 0 for m in members),
                "heat": round(heat),
                "status": status,
            })
        out.sort(key=lambda t: -t["heat"])
        return out

    @staticmethod
    async def _load_series(
        db: AsyncSession, board_type: str, days: int,
    ) -> tuple[list[date], dict[str, dict[date, BusinessBoardDaily]]]:
        """近 N 日板块快照序列：dates 降序 + {board_code: {record_date: row}}"""
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
            return [], {}
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
        return dates, series

    @staticmethod
    async def _load_limit_up_index(
        db: AsyncSession, window_dates: list[date], snapshot_date: date | None,
    ) -> dict:
        """近N日涨停池 -> 板块归属索引（名称口径 + 成分股口径并集）

        涨停池 industry 为东财口径板块名，与本库板块名（可能来自腾讯源）存在
        Ⅱ/Ⅲ 层级后缀差异，需归一化+去后缀匹配；成分股快照按 stock_code 归属
        可完全跨名称口径（涨停股计入其所属的全部行业/概念板块）。
        """
        rows = (await db.execute(
            select(
                BusinessLimitUpStock.industry,
                BusinessLimitUpStock.stock_code,
                BusinessLimitUpStock.consecutive_limit_up,
            ).where(
                BusinessLimitUpStock.record_date.in_(window_dates),
                BusinessLimitUpStock.deleted_at.is_(None),
            )
        )).all()
        if not rows:
            return {"by_name": {}, "by_board": {}}

        by_name: dict[str, dict[str, int]] = {}
        cons_by_code: dict[str, int] = {}
        lu_codes: set[str] = set()
        for industry, code, cons in rows:
            if not code:
                continue
            lu_codes.add(code)
            c = int(cons) if cons else 0
            cons_by_code[code] = max(cons_by_code.get(code, 0), c)
            if industry:
                norm = board_fetcher._norm_board_name(str(industry))
                for key in {norm, board_fetcher._strip_board_name_suffix(norm)}:
                    by_name.setdefault(key, {})[code] = max(
                        by_name.get(key, {}).get(code, 0), c
                    )

        by_board: dict[str, dict[str, int]] = {}
        if snapshot_date and lu_codes:
            snap = (await db.execute(
                select(
                    BusinessBoardStockDaily.board_code,
                    BusinessBoardStockDaily.stock_code,
                ).where(
                    BusinessBoardStockDaily.record_date == snapshot_date,
                    BusinessBoardStockDaily.stock_code.in_(lu_codes),
                    BusinessBoardStockDaily.deleted_at.is_(None),
                )
            )).all()
            for board_code, stock_code in snap:
                by_board.setdefault(board_code, {})[stock_code] = cons_by_code.get(stock_code, 0)
        return {"by_name": by_name, "by_board": by_board}

    @staticmethod
    def _calc_factors(
        dates: list[date],
        series: dict[str, dict[date, BusinessBoardDaily]],
        lu_index: dict,
    ) -> list[dict]:
        """板块因子计算（读时算）：涨幅/排名(含3日)/位置/量比/资金/涨停梯队/主题归属"""
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

        snapshot_date = dates[0]
        rank_now = _rank_map(snapshot_date)
        rank_total = len(rank_now) or 1
        rank_3d_ago = _rank_map(dates[2]) if len(dates) >= 3 else {}
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

        def _match_limit_up(board_code: str, board_name: str) -> tuple[int, int]:
            """涨停梯队：名称口径 ∪ 成分股口径（按股票代码去重），返回(家数, 最高连板)"""
            hits: dict[str, int] = {}
            norm = board_fetcher._norm_board_name(board_name)
            for key in (norm, board_fetcher._strip_board_name_suffix(norm)):
                hits.update(lu_index["by_name"].get(key, {}))
            hits.update(lu_index["by_board"].get(board_code, {}))
            return len(hits), max(hits.values(), default=0)

        factors: list[dict] = []
        for code, day_map in series.items():
            if snapshot_date not in day_map:
                continue
            today_row = day_map[snapshot_date]
            change_pct = _f(today_row.change_pct)
            gain_3d = _compound_gain([_f(day_map[d].change_pct) if d in day_map else None for d in dates[:3]])
            gain_5d = _compound_gain([_f(day_map[d].change_pct) if d in day_map else None for d in dates[:5]])
            gain_10d = gain10_map.get(code)

            rank = rank_now.get(code)
            rank_pct = round(rank / rank_total, 4) if rank is not None else None
            prev3, prev5 = rank_3d_ago.get(code), rank_5d_ago.get(code)
            rank_change_3d = (prev3 - rank) if (rank is not None and prev3 is not None) else None
            rank_change = (prev5 - rank) if (rank is not None and prev5 is not None) else None

            prev_turnovers = [
                v for v in (
                    _f(day_map[d].turnover) for d in dates[1:6] if d in day_map
                ) if v is not None
            ]
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

            limit_up_count, max_consecutive = _match_limit_up(code, today_row.board_name)

            position_pct = None
            if code in gain10_map and len(g10_vals) >= 5:
                position_pct = round(
                    bisect.bisect_left(g10_vals, gain10_map[code]) / len(g10_vals), 4
                )

            factors.append({
                "board_type": today_row.board_type,
                "board_code": code,
                "board_name": today_row.board_name,
                "change_pct": change_pct,
                "gain_3d": gain_3d,
                "gain_5d": gain_5d,
                "gain_10d": gain_10d,
                "rank": rank,
                "rank_pct": rank_pct,
                "rank_change": rank_change,
                "rank_change_3d": rank_change_3d,
                "volume_ratio": volume_ratio,
                "net_inflow": _f(today_row.net_inflow),
                "inflow_days": inflow_days,
                "limit_up_count": limit_up_count,
                "max_consecutive": max_consecutive,
                "position_pct": position_pct,
                "theme": _board_theme(today_row.board_name),
            })
        return factors

    @staticmethod
    async def get_overview(
        db: AsyncSession, board_type: str = "industry", days: int = 10,
    ) -> dict:
        """近期轮动板块总览：近 N 日快照现算主题热度/阶段/评分/操作建议

        主题热度跨行业+概念聚合（轮动以主题为单位展开，军工类主题的行业板块
        与概念板块需合并观察），对侧类型仅参与主题热度计算，不产生返回 items。
        """
        dates, series = await RotationService._load_series(db, board_type, days)
        if not dates:
            return RotationOverviewResponse(
                snapshot_date=None, history_days=0, items=[], themes=[],
            ).model_dump()
        snapshot_date = dates[0]

        other_type = "concept" if board_type == "industry" else "industry"
        other_dates, other_series = await RotationService._load_series(db, other_type, days)

        lu_index = await RotationService._load_limit_up_index(
            db, dates[:_LIMIT_UP_WINDOW], snapshot_date,
        )
        factors = RotationService._calc_factors(dates, series, lu_index)
        other_factors = (
            RotationService._calc_factors(other_dates, other_series, lu_index)
            if other_dates else []
        )
        themes = RotationService._calc_theme_heat(factors + other_factors)
        theme_by_name = {t["theme"]: t for t in themes}

        items: list[RotationOverviewItem] = []
        for f in factors:
            stage = _classify_stage(
                f["change_pct"], f["gain_3d"], f["gain_5d"], f["gain_10d"],
                f["rank_pct"], f["rank_change"], f["rank_change_3d"], f["inflow_days"],
            )
            f["stage"] = stage
            theme_stat = theme_by_name.get(f["theme"]) if f["theme"] else None
            score = _tomorrow_score(f, theme_stat)
            items.append(RotationOverviewItem(
                board_type=f["board_type"],
                board_code=f["board_code"],
                board_name=f["board_name"],
                change_pct=f["change_pct"],
                gain_3d=f["gain_3d"],
                gain_5d=f["gain_5d"],
                gain_10d=f["gain_10d"],
                rank=f["rank"],
                rank_change=f["rank_change"],
                volume_ratio=f["volume_ratio"],
                inflow_days=f["inflow_days"],
                limit_up_count=f["limit_up_count"],
                max_consecutive=f["max_consecutive"],
                stage=stage,
                tomorrow_score=score,
                action=_decide_action(stage, score, f["change_pct"]),
                theme=f["theme"],
                position_pct=f["position_pct"],
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
            themes=[RotationThemeItem(**t) for t in themes],
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
