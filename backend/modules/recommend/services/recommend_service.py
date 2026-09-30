#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 推荐股票服务 —— 综合六维度库内快照数据（涨停连板/热榜情绪/板块资金/轮动评分/
主力埋伏/超跌因子）+ 近24小时资讯，由 LLM 生成 10 只推荐股（涨停候选/抄底两类，
含预判买点），落库为 business_recommend_run/stock；同时把推荐写成专用策略
「AI每日推荐」的买入信号（business_strategy_signal），由每分钟交易引擎自动建仓
追踪，回测自动可回放。

执行流程异步化（与分析执行器一致）：
1. submit_run 创建 running 状态执行记录后立即返回（HTTP 请求毫秒级响应）
2. 候选收集与 LLM 生成在后台 asyncio 任务中进行（独立 session）
3. 本服务只产出推荐与待执行信号，不做买卖；模拟买卖由交易引擎按实时价执行
   （抄底类信号 entry_type=limit，实时价回落触及买点才成交）
"""
import asyncio
import json
import logging
import re
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode
from database.models.business.factor import BusinessFactor
from database.models.business.news import BusinessNews
from database.models.business.recommend import (
    BusinessRecommendRun,
    BusinessRecommendStock,
)
from database.models.business.strategy import (
    BusinessAiStrategy,
    BusinessStrategyRun,
    BusinessStrategySignal,
)
from database.models.sys.ai_model import AiFunctionEnum
from database.utils.timezone import timezone
from modules.agent.services.llm_client import resolve_model, stream_chat
from modules.recommend.schemas.recommend import (
    DIRECTION_BOTTOM_FISH,
    DIRECTION_LIMIT_UP,
    ENTRY_LIMIT,
    ENTRY_MARKET,
    REASON_DIMENSIONS,
)

logger = logging.getLogger(__name__)

# 后台生成整体超时（秒）：LLM 单轮流式不设总时长上限，这里兜底防止任务悬挂
RECOMMEND_TIMEOUT = 600

# 后台任务强引用集合（防止 asyncio.Task 被 GC），完成后自动移除
_BACKGROUND_TASKS: set[asyncio.Task] = set()

# 各维度候选取数规模（总量收敛到约 40 只）
_LIMIT_UP_TOP_N = 10
_HOT_SOURCES = ("em_rank", "ths_hot")
_HOT_TOP_N = 8
_FUND_BOARD_TOP_N = 3
_ROTATION_BOARD_TOP_N = 3
_BOARD_LEADING_N = 2
_BLOCK_TRADE_TOP_N = 10
_BLOCK_TRADE_WINDOW = "近一月"

# 资讯：近 N 小时重点资讯条数（与分析执行器口径一致）
_NEWS_HOURS = 24
_NEWS_LIMIT = 30
# 单只候选最多关联的资讯标题数
_NEWS_PER_STOCK = 2

# 抄底因子口径：bias20 超跌阈值(%) / rsi14 超卖阈值
_FACTOR_LOOKBACK = 60
_BIAS20_OVERSOLD = -6.0
_RSI14_OVERSOLD = 30.0
# 因子行情抓取整体超时（秒）：外部数据源逐票抓取慢，超时降级为无因子线索
_FACTOR_FETCH_TIMEOUT = 300

# 推荐个股数量
_RECOMMEND_COUNT = 10

# 专用策略（推荐信号落库到该策略下，交易引擎按信号自动建仓追踪）
_RECOMMEND_STRATEGY_NAME = "AI每日推荐"
# 新建专用策略时的默认风控参数（与 BusinessAiStrategy 列默认值一致）
_DEFAULT_STOP_LOSS_PCT = 5.0
_DEFAULT_TAKE_PROFIT_PCT = 10.0
_DEFAULT_TRAILING_DRAWDOWN_PCT = 5.0

_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 选股分析师，负责每日收盘后综合多维数据为A股选出 10 只次日推荐股。

我会提供从六个维度（涨停连板、热榜情绪、板块资金、轮动评分、主力埋伏、超跌因子）初筛的候选股池（含各维度量化线索与收盘快照价）以及近24小时重点财经资讯，禁止凭空编造数据与价格，推荐股必须来自候选池。

选股要求：
1. 两类方向：limit_up-涨停候选（强势接力：连板概率评分高/封单强/板块资金净流入/热榜靠前，预判买点贴近现价）；bottom_fish-抄底（超跌反弹：bias20/rsi14 超跌、主力大宗埋伏或有资讯催化，预判买点应低于现价，等回落介入）
2. 两类合计 10 只，比例按当日市场情绪灵活分配（涨停情绪强则涨停候选为主，情绪弱/退潮则抄底为主）
3. 每只给出：score 综合评分 0-100（越高越推荐）、buy_price 预判买点、target_price 目标价、stop_loss_price 止损价，必须满足 stop_loss_price < buy_price < target_price
4. 价格必须参考候选池中的 latest_price（收盘快照），buy_price 在其 ±3% 以内；抄底方向 buy_price 应低于 latest_price
5. reasons 六维度小结论逐条基于候选池线索撰写，无该维度线索的写「无」；summary 一句话推荐逻辑 40 字以内

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "stocks": [
    {
      "code": "600519",
      "name": "贵州茅台",
      "direction": "limit_up",
      "score": 85,
      "buy_price": 1500.0,
      "target_price": 1620.0,
      "stop_loss_price": 1430.0,
      "reasons": {
        "news": "资讯面小结论",
        "sentiment": "情绪面小结论",
        "factor": "因子面小结论",
        "sector_fund": "板块资金小结论",
        "main_force": "主力动向小结论",
        "limit_up": "涨停/连板小结论"
      },
      "summary": "一句话推荐逻辑"
    }
  ]
}
```
2. 再输出 markdown 综合研判报告，结构建议：
   ## 市场情绪定调（涨停/连板/资金面整体判断，决定两类配比）
   ## 涨停候选逻辑（重点标的逐一点评）
   ## 抄底候选逻辑（重点标的逐一点评）
   ## 风险提示

报告使用中文，条理清晰，总长度控制在 800 字以内。不构成投资建议的免责声明无需输出。
"""


def _extract_json_object(text: str) -> Optional[dict]:
    """从 LLM 回复中提取 JSON 对象（容忍 <think> 思考块 / ```json 代码块 / 前后杂文），
    失败返回 None（与分析执行器 _extract_json_object 同口径）"""
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    candidates = []
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        candidates.append(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _add_candidate(
    pool: dict[str, dict],
    code: str | None,
    name: str | None,
    source: str,
    latest_price: float | None = None,
    **clues,
) -> None:
    """候选池条目登记：按代码聚合，标注命中维度（sources）与量化线索（clues）"""
    code = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        return
    c = pool.setdefault(code, {
        "code": code, "name": (name or "").strip() or code,
        "sources": [], "latest_price": None, "clues": {},
    })
    if name and c["name"] == c["code"]:
        c["name"] = name.strip()
    if source not in c["sources"]:
        c["sources"].append(source)
    if latest_price and not c["latest_price"]:
        c["latest_price"] = round(float(latest_price), 4)
    c["clues"].update({k: v for k, v in clues.items() if v is not None})


def _to_float(value) -> Optional[float]:
    """宽松数值转换（LLM 偶发返回字符串/非法值），失败返回 None"""
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class RecommendService:
    """AI 推荐股票服务：submit_run 落库即返回，候选收集与 LLM 生成在后台任务中进行"""

    # ------------------------------------------------------------------
    # 提交与后台执行
    # ------------------------------------------------------------------
    @staticmethod
    async def submit_run(db: AsyncSession, trigger_type: str = "manual") -> int:
        """提交一次推荐生成：创建 running 状态执行记录并立即返回 run_id，
        候选收集与 LLM 生成在后台 asyncio 任务中进行（独立 session，只传 id）。

        并发守卫：当天已存在 running 记录时抛 RECOMMEND_ALREADY_RUNNING。
        """
        today = timezone.now().date()
        dup = await db.execute(
            select(BusinessRecommendRun.id).where(
                BusinessRecommendRun.run_date == today,
                BusinessRecommendRun.status == "running",
                BusinessRecommendRun.deleted_at.is_(None),
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.RECOMMEND_ALREADY_RUNNING,
                msg="今日推荐正在生成中，请稍后再试",
            )

        run = BusinessRecommendRun(
            run_date=today,
            trigger_type=trigger_type,
            status="running",
        )
        db.add(run)
        await db.commit()  # expire_on_commit=False，flush 后 run.id 可直接取用

        task = asyncio.create_task(RecommendService._execute(run.id))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        logger.info("已提交 AI 推荐生成: run_id=%s trigger=%s", run.id, trigger_type)
        return run.id

    @staticmethod
    async def _execute(run_id: int) -> None:
        """后台生成入口：独立 session + 整体超时兜底，任何异常都回写 Run 失败状态"""
        from database.db_manager import get_session

        async for db in get_session():
            try:
                await asyncio.wait_for(
                    RecommendService._run(db, run_id), timeout=RECOMMEND_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001  含 TimeoutError
                if isinstance(exc, asyncio.TimeoutError):
                    err_text = f"推荐生成超时（超过 {RECOMMEND_TIMEOUT} 秒）"
                else:
                    # 项目异常（CustomError 等）消息在 .msg 属性，str(exc) 可能为空
                    err_text = str(getattr(exc, "msg", None) or exc)
                logger.warning("AI 推荐生成失败: run_id=%s error=%s", run_id, err_text)
                try:
                    await db.rollback()
                    await db.execute(
                        update(BusinessRecommendRun)
                        .where(BusinessRecommendRun.id == run_id)
                        .values(status="failed", error_msg=err_text[:1000])
                        .execution_options(synchronize_session=False)
                    )
                    await db.commit()
                except Exception:  # noqa: BLE001
                    logger.exception("回写失败推荐记录异常: run_id=%s", run_id)

    @staticmethod
    async def _run(db: AsyncSession, run_id: int) -> None:
        """生成主体：收集候选 -> LLM 生成 -> 解析校验 -> 落推荐与买入信号"""
        run_result = await db.execute(
            select(BusinessRecommendRun).where(
                BusinessRecommendRun.id == run_id,
                BusinessRecommendRun.deleted_at.is_(None),
            )
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            logger.warning("推荐执行记录不存在，放弃生成: run_id=%s", run_id)
            return

        # 1. 收集六维度候选池（部分数据源失败不阻塞，快照中注明）
        snapshot = await RecommendService._collect_candidates(db)
        run.candidate_snapshot = snapshot

        # 2. LLM 生成（解析失败降级重试一次；原文独立提交落库，
        #    后续解析失败时外层 rollback 不会丢排查证据）
        user_prompt = RecommendService._build_user_prompt(snapshot)
        raw_text = await RecommendService._run_llm(db, user_prompt)
        run.ai_raw_response = raw_text[:20000]
        await db.commit()

        parsed = _extract_json_object(raw_text)
        if parsed is None or not isinstance(parsed.get("stocks"), list):
            logger.warning("推荐结果解析失败，降级重试一次: run_id=%s", run_id)
            raw_text = await RecommendService._run_llm(db, user_prompt)
            run.ai_raw_response = raw_text[:20000]
            await db.commit()
            parsed = _extract_json_object(raw_text)
            if parsed is None or not isinstance(parsed.get("stocks"), list):
                raise ValueError("无法从 AI 回复中解析出推荐 JSON")

        # 3. 校验修正（代码格式/方向枚举/评分区间/价格位 sanity/建仓方式推导）
        pool = {c["code"]: c for c in snapshot.get("candidates", [])}
        stocks = RecommendService._to_stocks(parsed, pool)
        if not stocks:
            raise ValueError("AI 推荐结果校验后为空（可能全部不在候选池或字段非法）")
        run.parsed_result = {"stocks": stocks}

        # 4. 落推荐个股 + 写策略买入信号（同事务提交）
        stock_rows: list[BusinessRecommendStock] = []
        for s in stocks:
            row = BusinessRecommendStock(
                run_id=run.id,
                rank=s["rank"],
                stock_code=s["code"],
                stock_name=s["name"],
                direction=s["direction"],
                score=s["score"],
                buy_price=s["buy_price"],
                target_price=s["target_price"],
                stop_loss_price=s["stop_loss_price"],
                entry_type=s["entry_type"],
                reasons=s["reasons"],
                summary=s["summary"],
            )
            db.add(row)
            stock_rows.append(row)
        await RecommendService._write_signals(db, run, stocks)
        for row, s in zip(stock_rows, stocks):
            row.signal_id = s.get("signal_id")

        run.status = "success"
        await db.commit()
        logger.info(
            "AI 推荐生成完成: run_id=%s stocks=%d limit_up=%d bottom_fish=%d",
            run_id, len(stocks),
            sum(1 for s in stocks if s["direction"] == DIRECTION_LIMIT_UP),
            sum(1 for s in stocks if s["direction"] == DIRECTION_BOTTOM_FISH),
        )

    # ------------------------------------------------------------------
    # 候选池收集（六维度，单维度失败不阻塞）
    # ------------------------------------------------------------------
    @staticmethod
    async def _collect_candidates(db: AsyncSession) -> dict:
        """从六个维度各取 top N 候选股（总量约 40 只），每只标注命中维度与量化线索，
        汇总为 candidate_snapshot dict（供 prompt 注入与落库回看）"""
        from modules.stock.services.limit_up_service import LimitUpService
        from modules.stock.services.stock_hot_service import StockHotService
        from modules.stock.services.board_service import BoardService
        from modules.stock.services.rotation_service import RotationService
        from modules.stock.services.block_trade_service import BlockTradeService

        pool: dict[str, dict] = {}
        warnings: list[str] = []

        # ---- 1. 涨停/连板池（按连板概率评分取前 N） ----
        try:
            items, _ = await LimitUpService.get_list(db, pool_type="limit_up", limit=60)
            top = sorted(
                items, key=lambda x: -(x.continuation_probability or 0),
            )[:_LIMIT_UP_TOP_N]
            for it in top:
                _add_candidate(
                    pool, it.stock_code, it.stock_name, "limit_up", it.latest_price,
                    consecutive_limit_up=it.consecutive_limit_up,
                    continuation_probability=it.continuation_probability,
                    seal_amount=float(it.seal_amount) if it.seal_amount is not None else None,
                    limit_up_reason=it.limit_up_reason,
                    industry=it.industry,
                )
        except Exception:  # noqa: BLE001
            logger.warning("推荐候选收集失败(limit_up，不阻塞)", exc_info=True)
            warnings.append("limit_up")

        # ---- 2. 热榜情绪（东财人气 + 同花顺热度，各取前 N） ----
        for source in _HOT_SOURCES:
            try:
                ranks = await StockHotService.get_rank_list(db, source)
                for it in ranks[:_HOT_TOP_N]:
                    _add_candidate(
                        pool, it.stock_code, it.stock_name, "sentiment", it.latest_price,
                        **{f"hot_rank_{source}": it.rank},
                        change_pct=it.change_pct,
                    )
            except Exception:  # noqa: BLE001
                logger.warning("推荐候选收集失败(hot:%s，不阻塞)", source, exc_info=True)
                warnings.append(f"sentiment:{source}")

        # ---- 3. 板块资金 + 轮动评分（强板块的前领涨股） ----
        try:
            fund_boards = await BoardService.get_list(
                db, board_type="industry", sort_by="net_inflow", sort_order="desc",
            )
            fund_boards = [
                b for b in fund_boards if b.net_inflow and float(b.net_inflow) > 0
            ][:_FUND_BOARD_TOP_N]
            for b in fund_boards:
                for ls in (b.leading_stocks or [])[:_BOARD_LEADING_N]:
                    _add_candidate(
                        pool, ls.code, ls.name, "sector_fund",
                        board_name=b.board_name,
                        board_net_inflow=float(b.net_inflow),
                        board_change_pct=b.change_pct,
                    )
        except Exception:  # noqa: BLE001
            logger.warning("推荐候选收集失败(sector_fund，不阻塞)", exc_info=True)
            warnings.append("sector_fund")

        try:
            ov = await RotationService.get_overview(db, board_type="industry", days=10)
            rotation_items = [
                it for it in (ov or {}).get("items") or []
                if it.get("action") in ("attack", "ambush")
            ][:_ROTATION_BOARD_TOP_N]
            if rotation_items:
                industry_boards = await BoardService.get_list(
                    db, board_type="industry", sort_by="change_pct", sort_order="desc",
                )
                by_name = {b.board_name: b for b in industry_boards}
                for rot in rotation_items:
                    b = by_name.get(rot.get("board_name"))
                    if b is None:
                        continue
                    for ls in (b.leading_stocks or [])[:_BOARD_LEADING_N]:
                        _add_candidate(
                            pool, ls.code, ls.name, "sector_fund",
                            board_name=b.board_name,
                            rotation_stage=rot.get("stage"),
                            tomorrow_score=rot.get("tomorrow_score"),
                            rotation_action=rot.get("action"),
                        )
        except Exception:  # noqa: BLE001
            logger.warning("推荐候选收集失败(rotation，不阻塞)", exc_info=True)
            warnings.append("rotation")

        # ---- 4. 主力埋伏（大宗交易活跃榜，含上榜后涨幅） ----
        try:
            actives = await BlockTradeService.get_active_list(db, _BLOCK_TRADE_WINDOW)
            for it in actives[:_BLOCK_TRADE_TOP_N]:
                _add_candidate(
                    pool, it.stock_code, it.stock_name, "main_force", it.latest_price,
                    list_count_total=it.list_count_total,
                    avg_change_5d=it.avg_change_5d,
                    avg_change_20d=it.avg_change_20d,
                )
        except Exception:  # noqa: BLE001
            logger.warning("推荐候选收集失败(main_force，不阻塞)", exc_info=True)
            warnings.append("main_force")

        # ---- 5. 近24小时资讯（匹配候选股名，命中即关联标题） ----
        news_rows: list[dict] = []
        try:
            since = timezone.now() - timedelta(hours=_NEWS_HOURS)
            result = await db.execute(
                select(BusinessNews)
                .where(
                    BusinessNews.published_at >= since,
                    BusinessNews.deleted_at.is_(None),
                )
                .order_by(BusinessNews.published_at.desc())
                .limit(_NEWS_LIMIT)
            )
            for n in result.scalars().all():
                news_rows.append({
                    "time": n.published_at.strftime("%m-%d %H:%M") if n.published_at else "",
                    "title": n.title,
                    "source": n.source_name,
                })
            for c in pool.values():
                if not c["name"] or c["name"] == c["code"]:
                    continue
                related = [
                    n["title"] for n in news_rows
                    if n["title"] and c["name"] in n["title"]
                ][:_NEWS_PER_STOCK]
                if related:
                    c["clues"]["related_news"] = related
                    if "news" not in c["sources"]:
                        c["sources"].append("news")
        except Exception:  # noqa: BLE001
            logger.warning("推荐候选收集失败(news，不阻塞)", exc_info=True)
            warnings.append("news")

        # ---- 6. 抄底因子（对候选池计算 bias20/rsi14，标注超跌） ----
        try:
            universe = list(pool.keys())
            if universe:
                values_by_factor = await RecommendService._calc_oversold_factors(
                    db, universe,
                )
                for c in pool.values():
                    bias = values_by_factor.get("bias20", {}).get(c["code"])
                    rsi = values_by_factor.get("rsi14", {}).get(c["code"])
                    clues = {}
                    if bias is not None:
                        clues["bias20"] = round(bias, 2)
                    if rsi is not None:
                        clues["rsi14"] = round(rsi, 2)
                    oversold = (
                        (bias is not None and bias <= _BIAS20_OVERSOLD)
                        or (rsi is not None and rsi <= _RSI14_OVERSOLD)
                    )
                    if oversold:
                        clues["oversold"] = True
                        if "factor" not in c["sources"]:
                            c["sources"].append("factor")
                    c["clues"].update(clues)
        except Exception:  # noqa: BLE001
            logger.warning("推荐候选收集失败(factor，不阻塞)", exc_info=True)
            warnings.append("factor")

        # 方向提示（供 LLM 参考，最终方向由 LLM 决定）：命中涨停维度→limit_up，
        # 超跌→bottom_fish
        for c in pool.values():
            if "limit_up" in c["sources"]:
                c["direction_hint"] = DIRECTION_LIMIT_UP
            elif c["clues"].get("oversold"):
                c["direction_hint"] = DIRECTION_BOTTOM_FISH

        candidates = sorted(
            pool.values(),
            key=lambda c: (-len(c["sources"]), c["code"]),
        )
        return {
            "generated_at": timezone.now().strftime("%Y-%m-%d %H:%M"),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "news": news_rows,
            "warnings": warnings,
        }

    @staticmethod
    async def _load_factors(db: AsyncSession, codes: tuple[str, ...]) -> dict:
        """按编码加载启用的预置因子（缺哪个跳过哪个，不阻塞）"""
        result = await db.execute(
            select(BusinessFactor).where(
                BusinessFactor.code.in_(codes),
                BusinessFactor.status == True,  # noqa: E712
                BusinessFactor.deleted_at.is_(None),
            )
        )
        return {f.code: f for f in result.scalars().all()}

    @staticmethod
    async def _calc_oversold_factors(db: AsyncSession, codes: list[str]) -> dict[str, dict[str, float]]:
        """对候选池一次性抓取行情并计算 bias20/rsi14，返回 {factor_code: {code: value}}；
        失败/超时返回空 dict（不阻塞）。

        直接复用 factor_calc 的行情抓取 + DSL 求值（而非两次 FactorCalcService.calc），
        避免两个因子各抓一遍全池行情（外部数据源慢，逐票抓取 40 只可能耗时数分钟）；
        整体以 _FACTOR_FETCH_TIMEOUT 兜底，超时降级为无因子线索。
        """
        from modules.factor.services.factor_calc import _fetch_universe_bars
        from modules.factor.services.formula import calc_factor_values

        factors = await RecommendService._load_factors(db, ("bias20", "rsi14"))
        if not factors:
            return {}
        try:
            bars_by_code, _target_day, _warnings = await asyncio.wait_for(
                _fetch_universe_bars(codes, None, _FACTOR_LOOKBACK),
                timeout=_FACTOR_FETCH_TIMEOUT,
            )
        except Exception:  # noqa: BLE001  含行情抓取失败/超时/池为空等，降级为无因子线索
            logger.warning("抄底因子行情抓取失败/超时（降级跳过）", exc_info=True)
            return {}
        values_by_factor: dict[str, dict[str, float]] = {}
        for code_name, factor in factors.items():
            try:
                values, _calc_warnings = calc_factor_values(factor.formula, bars_by_code)
            except Exception:  # noqa: BLE001
                logger.warning("因子计算失败(%s，降级跳过)", code_name, exc_info=True)
                continue
            values_by_factor[code_name] = {
                code: v for code, v in values.items() if v is not None
            }
        return values_by_factor

    # ------------------------------------------------------------------
    # LLM 生成与结果校验
    # ------------------------------------------------------------------
    @staticmethod
    async def _run_llm(db: AsyncSession, user_prompt: str) -> str:
        """单轮 LLM 调用（复用 agent 的模型解析，数据已注入 prompt，无需工具循环）"""
        resolved = await resolve_model(db, AiFunctionEnum.STOCK_PICKING)
        messages: list[dict] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        final_text = ""
        async for chunk in stream_chat(resolved, messages):
            if chunk.content:
                final_text += chunk.content
        return final_text

    @staticmethod
    def _build_user_prompt(snapshot: dict) -> str:
        """候选池快照 + 近24小时资讯 → user prompt"""
        parts = [
            f"当前时间：{snapshot.get('generated_at')}",
            "候选股池字段说明：sources-命中维度（limit_up-涨停连板/sentiment-热榜情绪/"
            "sector_fund-板块资金与轮动/main_force-主力大宗埋伏/news-资讯催化/factor-超跌因子），"
            "latest_price-收盘快照价，clues-量化线索（continuation_probability-连板概率评分0-100，"
            "consecutive_limit_up-连板数，seal_amount-封单金额，hot_rank_*-热榜排名，"
            "board_net_inflow-所属板块主力净流入(元)，tomorrow_score-板块明日评分0-100，"
            "rotation_action-板块轮动建议(attack-主攻/ambush-潜伏)，list_count_total-大宗上榜次数，"
            "avg_change_5d/20d-大宗上榜后均涨幅(%)，bias20-20日乖离率(%)，rsi14-14日RSI，"
            "oversold-是否超跌，related_news-相关资讯标题），direction_hint-维度初判方向提示。",
            "候选股池（推荐必须从中选取）：\n"
            + json.dumps(snapshot.get("candidates", []), ensure_ascii=False),
        ]
        news = snapshot.get("news") or []
        if news:
            lines = [f"- [{n['time']}] {n['title']}（{n['source']}）" for n in news]
            parts.append(
                f"近 {_NEWS_HOURS} 小时重点财经资讯（共 {len(lines)} 条，评估个股消息面时引用）：\n"
                + "\n".join(lines)
            )
        else:
            parts.append("近24小时资讯：暂无数据（请在报告中注明资讯面数据缺失）")
        if snapshot.get("warnings"):
            parts.append(f"数据缺失提示：以下维度收集失败已降级：{'、'.join(snapshot['warnings'])}")
        parts.append(
            f"请基于以上真实数据，输出 JSON 推荐结果（{_RECOMMEND_COUNT} 只）与 markdown 综合研判报告。"
        )
        return "\n\n".join(parts)

    @staticmethod
    def _to_stocks(parsed: dict, pool: dict[str, dict]) -> list[dict]:
        """LLM 推荐结果校验修正：代码格式/候选池归属/方向枚举/评分区间/价格位 sanity
        （止损<买点<目标，不满足按默认风控比例修正）/建仓方式推导；单条容错，
        按评分降序取前 _RECOMMEND_COUNT 只并赋 rank"""
        stocks: list[dict] = []
        for raw in parsed.get("stocks") or []:
            if not isinstance(raw, dict):
                continue
            code = str(raw.get("code") or raw.get("stock_code") or "").strip()
            if not re.fullmatch(r"\d{6}", code):
                continue
            candidate = pool.get(code)
            if candidate is None:
                # 防幻觉：候选池外的代码价格位不可信，丢弃
                logger.warning("推荐股不在候选池，丢弃: %s", code)
                continue

            direction = str(raw.get("direction") or "").strip().lower()
            if direction not in (DIRECTION_LIMIT_UP, DIRECTION_BOTTOM_FISH):
                direction = (
                    DIRECTION_LIMIT_UP
                    if "limit_up" in candidate["sources"]
                    else DIRECTION_BOTTOM_FISH
                )

            score = _to_float(raw.get("score"))
            score = max(0.0, min(100.0, score)) if score is not None else 50.0

            buy_price = _to_float(raw.get("buy_price"))
            if not buy_price or buy_price <= 0:
                buy_price = candidate.get("latest_price")
            if not buy_price or buy_price <= 0:
                logger.warning("推荐股无有效买点且候选池无快照价，丢弃: %s", code)
                continue

            target_price = _to_float(raw.get("target_price"))
            stop_loss_price = _to_float(raw.get("stop_loss_price"))
            # 价格位 sanity：止损必须低于买点、目标必须高于买点，不满足按默认风控比例修正
            if stop_loss_price is None or stop_loss_price >= buy_price:
                stop_loss_price = round(buy_price * (1 - _DEFAULT_STOP_LOSS_PCT / 100), 4)
            if target_price is None or target_price <= buy_price:
                target_price = round(buy_price * (1 + _DEFAULT_TAKE_PROFIT_PCT / 100), 4)

            # 建仓方式推导：抄底等回落触及买点（limit），涨停候选按实时价跟进（market）
            entry_type = ENTRY_LIMIT if direction == DIRECTION_BOTTOM_FISH else ENTRY_MARKET

            reasons_raw = raw.get("reasons") if isinstance(raw.get("reasons"), dict) else {}
            reasons = {
                dim: str(reasons_raw.get(dim) or "").strip()[:200] or "无"
                for dim in REASON_DIMENSIONS
            }

            stocks.append({
                "code": code,
                "name": str(raw.get("name") or candidate["name"]).strip()[:50],
                "direction": direction,
                "score": round(score, 2),
                "buy_price": round(buy_price, 4),
                "target_price": round(target_price, 4),
                "stop_loss_price": round(stop_loss_price, 4),
                "entry_type": entry_type,
                "reasons": reasons,
                "summary": str(raw.get("summary") or "").strip()[:500] or None,
            })

        # 按评分降序去重取前 N 并赋 rank
        dedup: dict[str, dict] = {}
        for s in sorted(stocks, key=lambda x: -x["score"]):
            dedup.setdefault(s["code"], s)
        result = list(dedup.values())[:_RECOMMEND_COUNT]
        for i, s in enumerate(result, 1):
            s["rank"] = i
        return result

    # ------------------------------------------------------------------
    # 信号落库（专用策略 + 终态 Run + 待执行买入信号）
    # ------------------------------------------------------------------
    @staticmethod
    async def _get_or_create_strategy(db: AsyncSession) -> BusinessAiStrategy:
        """按固定名称查/建推荐专用策略（prompt 型，股票池随每次推荐覆盖更新）"""
        result = await db.execute(
            select(BusinessAiStrategy).where(
                BusinessAiStrategy.name == _RECOMMEND_STRATEGY_NAME,
                BusinessAiStrategy.deleted_at.is_(None),
            ).limit(1)
        )
        strategy = result.scalar_one_or_none()
        if strategy is not None:
            return strategy
        strategy = BusinessAiStrategy(
            name=_RECOMMEND_STRATEGY_NAME,
            description="AI 推荐股票模块专用策略（由推荐任务自动维护股票池并落买入信号，"
                        "请勿手动执行/编辑）",
            category="general",
            is_preset=True,
            prompt_template="综合涨停连板/热榜情绪/板块资金/轮动评分/主力埋伏/超跌因子六维度，"
                            "每日推荐涨停候选与抄底两类个股（信号由 AI 推荐模块直接生成）。",
            stock_pool={"codes": []},
            execute_periods=["post_close"],
            max_positions=_RECOMMEND_COUNT,
            stop_loss_pct=_DEFAULT_STOP_LOSS_PCT,
            take_profit_pct=_DEFAULT_TAKE_PROFIT_PCT,
            trailing_drawdown_pct=_DEFAULT_TRAILING_DRAWDOWN_PCT,
            status=True,
            strategy_type="prompt",
        )
        db.add(strategy)
        await db.flush()
        logger.info("已创建推荐专用策略: strategy_id=%s", strategy.id)
        return strategy

    @staticmethod
    async def _write_signals(
        db: AsyncSession,
        run: BusinessRecommendRun,
        stocks: list[dict],
    ) -> None:
        """把推荐写成专用策略的买入信号：关联的 BusinessStrategyRun 直接落 success
        终态（running_key 生成列仅 running 记录占用 strategy_id 键位，避免与策略
        调度任务的 running 并发守卫冲突）；信号 run_date 沿用当日（与策略执行器一致，
        当日盘后产生的信号保留至下一交易日 15:05 由交易引擎执行/过期）"""
        strategy = await RecommendService._get_or_create_strategy(db)
        strategy.stock_pool = {"codes": [s["code"] for s in stocks]}
        today_str = run.run_date.strftime("%Y-%m-%d")

        strategy_run = BusinessStrategyRun(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            run_period="manual",
            run_date=today_str,
            trigger_type=run.trigger_type,
            status="success",
            ai_raw_response=(run.ai_raw_response or "")[:20000],
            parsed_signals=stocks,
        )
        db.add(strategy_run)
        await db.flush()

        # 作废同策略旧待执行信号（新一轮推荐信号替换旧信号，与策略执行器一致）
        await db.execute(
            update(BusinessStrategySignal)
            .where(
                BusinessStrategySignal.strategy_id == strategy.id,
                BusinessStrategySignal.status == "pending",
                BusinessStrategySignal.deleted_at.is_(None),
            )
            .values(status="expired", result_msg="被新一轮推荐信号替换")
            .execution_options(synchronize_session=False)
        )

        for s in stocks:
            sig = BusinessStrategySignal(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                run_id=strategy_run.id,
                run_period="manual",
                run_date=today_str,
                stock_code=s["code"],
                stock_name=s["name"],
                action="buy",
                ref_buy_price=s["buy_price"],
                target_sell_price=s["target_price"],
                stop_loss_price=s["stop_loss_price"],
                reason=s["summary"],
                entry_type=s["entry_type"],
                status="pending",
            )
            db.add(sig)
            await db.flush()
            s["signal_id"] = sig.id

        run.strategy_id = strategy.id

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @staticmethod
    async def get_latest(db: AsyncSession) -> Optional[tuple[BusinessRecommendRun, list]]:
        """获取最新一条推荐（含个股列表），无记录返回 None"""
        result = await db.execute(
            select(BusinessRecommendRun)
            .where(BusinessRecommendRun.deleted_at.is_(None))
            .order_by(BusinessRecommendRun.created_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return None
        stocks = await RecommendService._list_stocks(db, run.id)
        return run, stocks

    @staticmethod
    async def get_runs(db: AsyncSession, page: int, page_size: int) -> tuple[list, int]:
        """分页获取推荐历史记录，返回 (runs, total)"""
        total = (
            await db.execute(
                select(func.count())
                .select_from(BusinessRecommendRun)
                .where(BusinessRecommendRun.deleted_at.is_(None))
            )
        ).scalar() or 0
        result = await db.execute(
            select(BusinessRecommendRun)
            .where(BusinessRecommendRun.deleted_at.is_(None))
            .order_by(BusinessRecommendRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_run_detail(
        db: AsyncSession, run_id: int
    ) -> tuple[BusinessRecommendRun, list]:
        """获取推荐记录详情（run + stocks），不存在抛 RECOMMEND_RUN_NOT_FOUND"""
        result = await db.execute(
            select(BusinessRecommendRun).where(
                BusinessRecommendRun.id == run_id,
                BusinessRecommendRun.deleted_at.is_(None),
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise CustomError(
                error=CustomErrorCode.RECOMMEND_RUN_NOT_FOUND,
                msg="推荐记录不存在或已删除",
            )
        stocks = await RecommendService._list_stocks(db, run.id)
        return run, stocks

    @staticmethod
    async def _list_stocks(db: AsyncSession, run_id: int) -> list:
        result = await db.execute(
            select(BusinessRecommendStock).where(
                BusinessRecommendStock.run_id == run_id,
                BusinessRecommendStock.deleted_at.is_(None),
            ).order_by(BusinessRecommendStock.rank.asc())
        )
        return list(result.scalars().all())
