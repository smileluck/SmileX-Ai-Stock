#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略执行器 —— 调用 LLM（复用 agent 模块模型解析 + 工具注册表），
产出结构化买卖信号并落库为待执行信号（business_strategy_signal）。

执行流程异步化：
1. submit_run 创建 running 状态执行记录后立即返回（HTTP 请求毫秒级响应，
   不再被 LLM 长耗时拖超时）
2. LLM 分析在后台 asyncio 任务中进行（独立 session）
3. 分析只产出待执行信号，不做买卖；模拟买卖由每分钟交易引擎
   （modules/strategy/services/trade_engine.py）按实时价执行
"""
import asyncio
import json
import logging
import re
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.response.response_code import CustomErrorCode
from core.exception.errors import CustomError
from database.models.business.strategy import (
    BusinessAiStrategy,
    BusinessStrategyRun,
    BusinessStrategyPosition,
    BusinessStrategySignal,
)
from database.utils.timezone import timezone
from modules.agent.services.llm_client import resolve_model, stream_chat
from modules.agent.services.tool_registry import get_openai_format, execute
from modules.strategy.schemas.strategy import SignalItem
from modules.strategy.services.quote_helper import fetch_latest_prices
logger = logging.getLogger(__name__)

# ReAct 最大迭代轮数（与 agent_service 保持一致）
MAX_ITERATIONS = 8

# 后台分析整体超时（秒）：LLM 单轮流式不设总时长上限，这里兜底防止任务悬挂
ANALYSIS_TIMEOUT = 600

# 后台任务强引用集合（防止 asyncio.Task 被 GC），完成后自动移除
_BACKGROUND_TASKS: set[asyncio.Task] = set()

# 系统提示词：要求 LLM 基于工具真实数据输出严格 JSON 信号
SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 策略分析师，负责按用户策略对A股市场进行买卖点分析。

你可以调用以下工具获取系统中的真实数据：
- get_hot_stocks: 股票热榜（东财/同花顺/雪球等热度排名）
- get_market_indices: 大盘指数行情
- get_market_fund_flow: 大盘资金流向
- get_index_history: 大盘指数历史K线（判断指数趋势）
- get_board_ranking: 行业/概念板块涨跌幅排行
- get_limit_up_stocks: 涨停股池
- get_index_constituents: 指数成分股列表（沪深300/中证500，蓝筹白马选股参考）
- get_latest_news: 最新财经新闻
- get_research_reports: 个股近期券商研报列表（评级/盈利预测 EPS/PE/机构/日期）
- get_report_consensus: 个股研报共识（评级分布/覆盖机构数/最新评级时间线）

工作流程：
1. 先调用工具获取真实行情数据，禁止凭空编造价格和数据
2. 结合当前持仓情况，按策略要求给出信号
3. buy_price 必须以用户消息中提供的「实时行情快照」最新价为基准（可在 ±2% 内小幅浮动），
   严禁使用历史价/记忆中的价格；若快照缺失某股实时价，不得给出该股的 buy 信号
4. 止损价必须低于 buy_price、目标价必须高于 buy_price，且严格按策略风控比例设置
5. 若个股已较近期低点大幅拉升（追高风险明显），宁可放弃信号也不要追高买入
6. 持仓卖出研判：当前封死涨停（涨跌幅达涨停位）的持仓不要给出 sell——连板潜力需保留
   （等开板走弱或次日再评估）；但高位炸板、放量滞涨、尾盘跳水的持仓应果断 sell

最终必须输出一个 JSON 数组（可包在 ```json 代码块中），每个元素格式如下：
[
  {
    "stock_code": "600519",            // 6位证券代码
    "stock_name": "贵州茅台",
    "action": "buy",                   // buy-新买入 / sell-卖出平仓 / adjust-调整持仓卖点 / hold-继续持有（无点位变化）
    "buy_price": 1500.0,               // 买入参考价（action=buy 时必填）
    "target_sell_price": 1620.0,       // 预估卖点/目标价（buy/adjust 时填写）
    "stop_loss_price": 1430.0,         // 止损价（buy/adjust 时填写）
    "reason": "缩量回调至10日线，资金回流"  // 简要理由
  }
]

没有合适的信号时输出空数组 []。除 JSON 外不要输出任何多余文字。回答使用中文。
"""


def _extract_json_array(text: str) -> list[dict]:
    """从 LLM 回复中提取 JSON 数组（容忍 <think> 思考块 / ```json 代码块 / 前后杂文）"""
    if not text:
        return []
    # 思考模型（如 MiniMax-M3）的英文思考块常含方括号，先剥离再提取，
    # 否则"第一个 [ 到最后一个 ]"会混入思考文字导致解析失败
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # 优先取 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidates = []
    if m:
        candidates.append(m.group(1))
    # 否则取第一个 [ 到最后一个 ] 之间的内容
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("无法从 AI 回复中解析出 JSON 数组")


def _to_signal(raw: dict) -> Optional[SignalItem]:
    """单条原始信号 → SignalItem，非法条目返回 None"""
    code = str(raw.get("stock_code") or "").strip()
    action = str(raw.get("action") or "").strip().lower()
    if not re.fullmatch(r"\d{6}", code) or action not in ("buy", "sell", "adjust", "hold"):
        return None
    return SignalItem(
        stock_code=code,
        stock_name=str(raw.get("stock_name") or "").strip()[:50],
        action=action,
        buy_price=float(raw["buy_price"]) if raw.get("buy_price") not in (None, "", 0) else None,
        target_sell_price=float(raw["target_sell_price"]) if raw.get("target_sell_price") else None,
        stop_loss_price=float(raw["stop_loss_price"]) if raw.get("stop_loss_price") else None,
        reason=str(raw.get("reason") or "").strip()[:500] or None,
    )


async def _run_llm(db: AsyncSession, user_prompt: str) -> str:
    """带工具调用的 LLM 循环（复用 agent 的 ReAct 模式，非流式消费），返回最终文本"""
    # 触发工具模块导入，完成注册
    from modules.agent.tools import stock_tools, news_tools, research_report_tools  # noqa: F401

    from database.models.sys.ai_model import AiFunctionEnum

    resolved = await resolve_model(db, AiFunctionEnum.STOCK_PICKING)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    tools = get_openai_format()
    final_text = ""

    for _ in range(MAX_ITERATIONS):
        collected_tool_calls: list[dict] = []
        assistant_text = ""

        async for chunk in stream_chat(resolved, messages, tools):
            if chunk.content:
                assistant_text += chunk.content
            if chunk.tool_calls:
                collected_tool_calls = chunk.tool_calls

        if not collected_tool_calls:
            final_text = assistant_text
            break

        messages.append(
            {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(
                                tc.get("arguments", {}), ensure_ascii=False
                            ),
                        },
                    }
                    for tc in collected_tool_calls
                ],
            }
        )
        for tc in collected_tool_calls:
            result = await execute(tc["name"], tc.get("arguments", {}) or {}, db)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    else:
        raise CustomError(
            error=CustomErrorCode.AGENT_MAX_ITERATIONS,
            msg="策略分析达到最大工具调用轮数，未产出最终结论",
        )

    return final_text


def _build_user_prompt(
    strategy: BusinessAiStrategy,
    holdings: list[BusinessStrategyPosition],
    run_period_name: str,
    realtime_quotes: dict[str, float] | None = None,
    is_review: bool = False,
) -> str:
    parts = [
        f"当前执行时段：{run_period_name}，当前时间：{timezone.now().strftime('%Y-%m-%d %H:%M')}",
        f"策略名称：{strategy.name}",
    ]
    if strategy.description:
        parts.append(f"策略描述：{strategy.description}")
    parts.append(f"策略要求：{strategy.prompt_template or '无特殊要求，按市场热点与技术面自主选股'}")

    pool = (strategy.stock_pool or {}).get("codes") if strategy.stock_pool else None
    if pool:
        parts.append(f"候选股票池（仅允许在该池内选择）：{', '.join(str(c) for c in pool)}")

    parts.append(f"最大同时持仓数：{strategy.max_positions}（当前已持仓 {len(holdings)} 只，不要超限）")

    # 注入策略风控比例，约束 AI 设置的止损/止盈价格位
    if strategy.stop_loss_pct is not None or strategy.take_profit_pct is not None:
        parts.append(
            "风控要求："
            + (
                f"止损比例约 {float(strategy.stop_loss_pct):g}%（相对买价）"
                if strategy.stop_loss_pct is not None else ""
            )
            + (
                f"，止盈目标约 {float(strategy.take_profit_pct):g}%"
                if strategy.take_profit_pct is not None else ""
            )
            + "，请据此设置 stop_loss_price / target_sell_price，不得明显偏离"
        )

    if holdings:
        hold_lines = []
        for h in holdings:
            cur = realtime_quotes.get(h.stock_code) if realtime_quotes else None
            chg = f"{(cur / float(h.buy_price) - 1) * 100:+.1f}%" if cur else "未知"
            # 回撤止盈上下文：持仓期间峰值与距峰值的回撤幅度
            trail = ""
            if h.peak_price is not None and h.trailing_drawdown_pct is not None and cur:
                peak = float(h.peak_price)
                dd = (peak - cur) / peak * 100 if peak > 0 else 0.0
                trail = (f"，持仓峰值 {peak:g}（距峰值 {dd:+.1f}%，"
                         f"回撤止盈线 {float(h.trailing_drawdown_pct):g}%）")
            hold_lines.append(
                f"- {h.stock_code} {h.stock_name}：买价 {h.buy_price}，"
                f"现价相对买价 {chg}{trail}，"
                f"预估卖点 {h.target_sell_price or '无'}，止损价 {h.stop_loss_price or '无'}"
            )
        parts.append("当前持仓（对已持仓个股请重点评估是否卖出/调整卖点，action=sell 或 adjust）：\n" + "\n".join(hold_lines))

    # 实时行情快照：工具数据多为收盘后快照，盘中决策与 buy_price 必须以本快照最新价为准
    if realtime_quotes:
        quote_lines = [f"- {code}: {price}" for code, price in sorted(realtime_quotes.items())]
        parts.append(
            "实时行情快照（新浪实时接口，生成于本次分析时刻；buy_price 必须以此为准，"
            "快照中缺失实时价的个股禁止给出 buy 信号）：\n" + "\n".join(quote_lines)
        )
    else:
        parts.append("注意：实时行情快照获取失败，此时禁止给出任何 buy 信号（只可评估持仓卖出/调整）。")

    if is_review:
        parts.append(
            "本轮为涨停保护或浮盈回撤预警触发的盘中持仓复核：重点评估已持仓个股是"
            "保留（hold）、上移卖点/止损锁定利润（adjust），还是炸板/滞涨/冲高回落/"
            "尾盘走弱兑现离场（sell）；若现价距持仓峰值回撤已接近或超过回撤止盈线，"
            "优先考虑 sell 或上移止损保护利润；除非出现极高把握的机会，本轮不要给出新买入信号。"
        )

    parts.append("请基于工具获取的最新真实数据，输出 JSON 信号数组。")
    return "\n".join(parts)


class StrategyExecutor:
    """策略执行器：submit_run 落库即返回，LLM 分析在后台任务中进行，
    产出待执行信号；模拟买卖由每分钟交易引擎按实时价执行"""

    @staticmethod
    async def submit_run(
        db: AsyncSession,
        strategy: BusinessAiStrategy,
        run_period: str,
        trigger_type: str = "schedule",
    ) -> int:
        """提交一次策略执行：创建 running 状态执行记录并立即返回 run_id，
        LLM 分析在后台 asyncio 任务中进行（独立 session，只传 id 不传 ORM 实例）。

        同一策略并发守卫：已存在 running 记录时抛 STRATEGY_ALREADY_RUNNING。
        """
        dup = await db.execute(
            select(BusinessStrategyRun.id).where(
                BusinessStrategyRun.strategy_id == strategy.id,
                BusinessStrategyRun.status == "running",
                BusinessStrategyRun.deleted_at.is_(None),
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_ALREADY_RUNNING,
                msg="该策略正在执行中，请稍后再试",
            )

        now = timezone.now()
        run = BusinessStrategyRun(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            run_period=run_period,
            run_date=now.strftime("%Y-%m-%d"),
            trigger_type=trigger_type,
            status="running",
        )
        db.add(run)
        strategy.last_executed_at = now
        await db.commit()  # expire_on_commit=False，flush 后 run.id 可直接取用

        task = asyncio.create_task(
            StrategyExecutor._execute_analysis(run.id, strategy.id, run_period)
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        logger.info(
            "已提交策略执行: strategy=%s run_id=%s period=%s trigger=%s",
            strategy.name, run.id, run_period, trigger_type,
        )
        return run.id

    # ------------------------------------------------------------------
    # 后台分析
    # ------------------------------------------------------------------
    @staticmethod
    async def _execute_analysis(run_id: int, strategy_id: int, run_period: str) -> None:
        """后台分析入口：独立 session + 整体超时兜底，任何异常都回写 Run 失败状态"""
        from database.db_manager import get_session

        async for db in get_session():
            try:
                await asyncio.wait_for(
                    StrategyExecutor._analyze(db, run_id, strategy_id, run_period),
                    timeout=ANALYSIS_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001  含 TimeoutError
                if isinstance(exc, asyncio.TimeoutError):
                    err_text = f"分析执行超时（超过 {ANALYSIS_TIMEOUT} 秒）"
                else:
                    # 项目异常（CustomError 等）消息在 .msg 属性，str(exc) 可能为空
                    err_text = str(getattr(exc, "msg", None) or exc)
                logger.warning("策略后台分析失败: run_id=%s error=%s", run_id, err_text)
                try:
                    await db.rollback()
                    await db.execute(
                        update(BusinessStrategyRun)
                        .where(BusinessStrategyRun.id == run_id)
                        .values(status="failed", error_msg=err_text[:1000])
                        .execution_options(synchronize_session=False)
                    )
                    await db.commit()
                except Exception:  # noqa: BLE001
                    logger.exception("回写失败 Run 记录异常: run_id=%s", run_id)

    @staticmethod
    async def _analyze(
        db: AsyncSession, run_id: int, strategy_id: int, run_period: str
    ) -> None:
        """分析主体：LLM 生成信号 -> 作废旧待执行信号 -> 写入新待执行信号。

        本步不做任何买卖 —— 模拟买卖由交易引擎每分钟按实时价执行。
        """
        from modules.strategy.schemas.strategy import EXECUTE_PERIOD_NAMES

        run_result = await db.execute(
            select(BusinessStrategyRun).where(
                BusinessStrategyRun.id == run_id,
                BusinessStrategyRun.deleted_at.is_(None),
            )
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            logger.warning("策略执行记录不存在，放弃分析: run_id=%s", run_id)
            return

        str_result = await db.execute(
            select(BusinessAiStrategy).where(
                BusinessAiStrategy.id == strategy_id,
                BusinessAiStrategy.deleted_at.is_(None),
            )
        )
        strategy = str_result.scalar_one_or_none()
        if strategy is None:
            run.status = "failed"
            run.error_msg = "策略不存在或已删除"
            await db.commit()
            return

        # 1. 取当前持仓
        hold_result = await db.execute(
            select(BusinessStrategyPosition).where(
                BusinessStrategyPosition.strategy_id == strategy.id,
                BusinessStrategyPosition.status == "holding",
                BusinessStrategyPosition.deleted_at.is_(None),
            )
        )
        holdings = list(hold_result.scalars().all())

        # 2. 拉取候选股实时行情（股票池 ∪ 持仓股，新浪实时接口）
        #    AI 工具数据多为收盘后快照，buy_price 参考价必须锚定实时价，防过期/幻觉价
        pool = (strategy.stock_pool or {}).get("codes") if strategy.stock_pool else None
        quote_codes = list({str(c) for c in (pool or [])} | {h.stock_code for h in holdings})
        realtime_quotes: dict[str, float] = {}
        if quote_codes:
            try:
                realtime_quotes = await fetch_latest_prices(quote_codes)
            except Exception:  # noqa: BLE001
                logger.warning("策略分析实时行情拉取失败: strategy=%s", strategy.name, exc_info=True)
                realtime_quotes = {}

        # 3. LLM 分析（原文独立提交落库：后续解析失败时外层 rollback 不会丢排查证据）
        user_prompt = _build_user_prompt(
            strategy, holdings, EXECUTE_PERIOD_NAMES.get(run_period, run_period),
            realtime_quotes=realtime_quotes,
            is_review=(run_period == "review"),
        )
        raw_text = await _run_llm(db, user_prompt)
        run.ai_raw_response = raw_text[:20000]
        await db.commit()

        # 4. 解析信号（思考模型偶发响应截断/格式偏差，解析失败降级重试一次）
        try:
            raw_signals = _extract_json_array(raw_text)
        except ValueError:
            logger.warning(
                "策略信号解析失败，降级重试一次: strategy=%s run_id=%s",
                strategy.name, run_id,
            )
            raw_text = await _run_llm(db, user_prompt)
            run.ai_raw_response = raw_text[:20000]
            await db.commit()
            raw_signals = _extract_json_array(raw_text)
        signals = [s for s in (_to_signal(r) for r in raw_signals if isinstance(r, dict)) if s]
        run.parsed_signals = [s.model_dump() for s in signals]

        # 5. 作废同策略旧待执行信号（新一轮分析信号替换旧信号）
        await db.execute(
            update(BusinessStrategySignal)
            .where(
                BusinessStrategySignal.strategy_id == strategy.id,
                BusinessStrategySignal.status == "pending",
                BusinessStrategySignal.deleted_at.is_(None),
            )
            .values(status="expired", result_msg="被新一轮分析信号替换")
            .execution_options(synchronize_session=False)
        )

        # 6. 写入新待执行信号（hold 无点位变化，不落表）
        pending = 0
        for sig in signals:
            if sig.action == "hold":
                continue
            db.add(BusinessStrategySignal(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                run_id=run.id,
                run_period=run_period,
                run_date=run.run_date,
                stock_code=sig.stock_code,
                stock_name=sig.stock_name or sig.stock_code,
                action=sig.action,
                ref_buy_price=sig.buy_price,
                target_sell_price=sig.target_sell_price,
                stop_loss_price=sig.stop_loss_price,
                reason=sig.reason,
                status="pending",
            ))
            pending += 1

        run.status = "success"
        await db.commit()
        logger.info(
            "策略分析完成: strategy=%s period=%s signals=%d pending_signals=%d",
            strategy.name, run_period, len(signals), pending,
        )
