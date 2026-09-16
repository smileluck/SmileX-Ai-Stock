#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
规则型策略执行器 —— 与 StrategyExecutor 相同的异步提交模式：
1. submit_run 创建 running 记录后立即返回 run_id（并发守卫口径与 prompt 型一致；
   同日同时段去重由调度方负责）
2. 后台任务中按 rule_config 的因子条件评估股票池 + 当前持仓，生成 buy/sell 信号
3. 信号落 business_strategy_signal，由每分钟交易引擎按实时价执行（与 prompt 型一致）

评估口径：
- universe = 策略股票池 codes ∪ 当前持仓代码（规则型必须有显式股票池，创建时已校验）
- 因子值取最近交易日（lookback=120），复用 factor 模块的行情抓取与 DSL 求值
- buy：池内未持仓且满足全部 buy_conditions，且买入信号数不超 max_positions 剩余槽位
  （ref_buy_price=基准日收盘价，止损/目标价按策略 pct 折算）
- sell：持仓满足全部 sell_conditions（sell_conditions 为空则不产规则卖出信号，
  机械离场由交易引擎的止损/止盈/回撤处理）
"""
import asyncio
import logging
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode
from database.models.business.factor import BusinessFactor
from database.models.business.strategy import (
    BusinessAiStrategy,
    BusinessStrategyPosition,
    BusinessStrategyRun,
    BusinessStrategySignal,
)
from database.utils.timezone import timezone
from modules.factor.services.factor_calc import _fetch_universe_bars, _latest_stock_names
from modules.factor.services.formula import calc_factor_values

logger = logging.getLogger(__name__)

# 后台评估整体超时（秒）：baostock 串行抓取多票日线可能较慢，兜底防悬挂
RULE_EVAL_TIMEOUT = 600

# 因子计算统一回看交易日数
RULE_LOOKBACK = 120

# 后台任务强引用集合（防止 asyncio.Task 被 GC），完成后自动移除
_BACKGROUND_TASKS: set[asyncio.Task] = set()

_OP_SYMBOLS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    return False


def _match_all(
    conds: list[dict],
    values_by_fid: dict[int, dict[str, float]],
    factor_codes: dict[int, str],
    code: str,
) -> tuple[bool, list[str]]:
    """全部条件 AND；任一因子值缺失视为不满足。返回 (是否命中, 条件明细文本)"""
    details: list[str] = []
    for cond in conds:
        value = values_by_fid.get(cond["factor_id"], {}).get(code)
        if value is None:
            return False, details
        fid = cond["factor_id"]
        details.append(
            f"{factor_codes.get(fid, fid)} {_OP_SYMBOLS.get(cond['op'], cond['op'])} "
            f"{cond['value']}（实际 {value}）"
        )
        if not _compare(value, cond["op"], cond["value"]):
            return False, details
    return True, details


class RuleExecutor:
    """规则型策略执行器"""

    @staticmethod
    async def submit_run(
        db: AsyncSession,
        strategy: BusinessAiStrategy,
        run_period: str,
        trigger_type: str = "schedule",
    ) -> int:
        """提交一次规则评估：创建 running 状态执行记录并立即返回 run_id，
        评估在后台 asyncio 任务中进行（独立 session，只传 id 不传 ORM 实例）。

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
            RuleExecutor._execute_eval(run.id, strategy.id, run_period)
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        return run.id

    # ------------------------------------------------------------------
    # 后台执行
    # ------------------------------------------------------------------
    @staticmethod
    async def _execute_eval(run_id: int, strategy_id: int, run_period: str) -> None:
        """后台评估入口：独立 session + 整体超时兜底，任何异常都回写 Run 失败状态"""
        from database.db_manager import get_session

        async for db in get_session():
            try:
                await asyncio.wait_for(
                    RuleExecutor._evaluate(db, run_id, strategy_id, run_period),
                    timeout=RULE_EVAL_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001  含 TimeoutError
                if isinstance(exc, asyncio.TimeoutError):
                    err_text = f"规则评估超时（超过 {RULE_EVAL_TIMEOUT} 秒）"
                else:
                    # 项目异常（CustomError 等）消息在 .msg 属性，str(exc) 可能为空
                    err_text = str(getattr(exc, "msg", None) or exc)
                logger.warning("规则策略评估失败: run_id=%s error=%s", run_id, err_text)
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
    async def _evaluate(
        db: AsyncSession, run_id: int, strategy_id: int, run_period: str
    ) -> None:
        """评估主体：因子条件判定 -> 作废旧待执行信号 -> 写入新待执行信号。

        本步不做任何买卖 —— 模拟买卖由交易引擎每分钟按实时价执行。
        """
        run_result = await db.execute(
            select(BusinessStrategyRun).where(
                BusinessStrategyRun.id == run_id,
                BusinessStrategyRun.deleted_at.is_(None),
            )
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            logger.warning("执行记录不存在，放弃评估: run_id=%s", run_id)
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

        cfg = strategy.rule_config or {}
        buy_conds: list[dict] = cfg.get("buy_conditions") or []
        sell_conds: list[dict] = cfg.get("sell_conditions") or []
        if not buy_conds:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_RULE_CONFIG_INVALID,
                msg="规则型策略未配置买入条件",
            )

        pool_codes: list[str] = (strategy.stock_pool or {}).get("codes") or []
        if not pool_codes:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_RULE_NO_POOL,
                msg="规则型策略必须配置非空股票池",
            )

        # 当前持仓（universe 需并入，供卖出条件评估）
        pos_result = await db.execute(
            select(BusinessStrategyPosition).where(
                BusinessStrategyPosition.strategy_id == strategy.id,
                BusinessStrategyPosition.status == "holding",
                BusinessStrategyPosition.deleted_at.is_(None),
            )
        )
        holdings = list(pos_result.scalars().all())
        holding_codes = {p.stock_code for p in holdings}

        universe = list(dict.fromkeys([*pool_codes, *holding_codes]))
        bars_by_code, target_day, warnings = await _fetch_universe_bars(
            universe, None, RULE_LOOKBACK
        )

        # 逐因子计算（同一因子多条件只算一次）
        factor_ids = {c["factor_id"] for c in buy_conds + sell_conds}
        fac_result = await db.execute(
            select(BusinessFactor).where(
                BusinessFactor.id.in_(factor_ids),
                BusinessFactor.deleted_at.is_(None),
            )
        )
        factors = {f.id: f for f in fac_result.scalars().all()}
        missing = factor_ids - factors.keys()
        if missing:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_RULE_CONFIG_INVALID,
                msg=f"因子不存在或已删除: {sorted(missing)}",
            )
        factor_codes = {fid: f.code for fid, f in factors.items()}
        values_by_fid: dict[int, dict[str, float]] = {}
        for fid, factor in factors.items():
            values, calc_warnings = calc_factor_values(factor.formula, bars_by_code)
            warnings.extend(calc_warnings)
            values_by_fid[fid] = values

        closes = {
            code: bars[-1].get("close")
            for code, bars in bars_by_code.items()
            if bars
        }
        names = await _latest_stock_names(db, universe)

        # ---- 卖出信号：持仓满足全部 sell_conditions ----
        new_signals: list[dict[str, Any]] = []
        for pos in holdings:
            if not sell_conds:
                continue
            ok, details = _match_all(sell_conds, values_by_fid, factor_codes, pos.stock_code)
            if ok:
                new_signals.append({
                    "stock_code": pos.stock_code,
                    "stock_name": pos.stock_name,
                    "action": "sell",
                    "reason": "规则卖出：" + "；".join(details),
                })

        # ---- 买入信号：池内未持仓 + 满足全部 buy_conditions + 剩余槽位 ----
        remaining_slots = max(strategy.max_positions - len(holdings), 0)
        stop_loss_pct = float(strategy.stop_loss_pct) if strategy.stop_loss_pct is not None else None
        take_profit_pct = float(strategy.take_profit_pct) if strategy.take_profit_pct is not None else None
        for code in pool_codes:
            if remaining_slots <= 0:
                break
            if code in holding_codes or code not in bars_by_code:
                continue
            ok, details = _match_all(buy_conds, values_by_fid, factor_codes, code)
            if not ok:
                continue
            close = closes.get(code)
            if not close:
                continue
            new_signals.append({
                "stock_code": code,
                "stock_name": names.get(code, "") or code,
                "action": "buy",
                "ref_buy_price": round(float(close), 4),
                "stop_loss_price": (
                    round(float(close) * (1 - stop_loss_pct / 100), 4)
                    if stop_loss_pct is not None else None
                ),
                "target_sell_price": (
                    round(float(close) * (1 + take_profit_pct / 100), 4)
                    if take_profit_pct is not None else None
                ),
                "reason": "规则买入：" + "；".join(details),
            })
            remaining_slots -= 1

        # ---- 作废同策略旧 pending 信号，写入新信号（口径同 prompt 型） ----
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
        run_date = run.run_date
        for sig in new_signals:
            db.add(BusinessStrategySignal(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                run_id=run.id,
                run_period=run_period,
                run_date=run_date,
                status="pending",
                **sig,
            ))

        buy_count = sum(1 for s in new_signals if s["action"] == "buy")
        sell_count = sum(1 for s in new_signals if s["action"] == "sell")
        cond_text = lambda conds: " 且 ".join(  # noqa: E731
            f"{factor_codes.get(c['factor_id'], c['factor_id'])} "
            f"{_OP_SYMBOLS.get(c['op'], c['op'])} {c['value']}" for c in conds
        )
        summary_lines = [
            f"规则评估完成（基准日 {target_day}，universe {len(universe)} 只，"
            f"持仓 {len(holdings)} 只）",
            f"买入条件：{cond_text(buy_conds)}",
            f"卖出条件：{cond_text(sell_conds) if sell_conds else '（未配置，仅机械离场）'}",
            f"信号：买入 {buy_count} 条，卖出 {sell_count} 条",
        ]
        if warnings:
            summary_lines.append("告警：" + "；".join(warnings[:20]))
        run.ai_raw_response = "\n".join(summary_lines)
        run.parsed_signals = [
            {
                "stock_code": s["stock_code"],
                "stock_name": s["stock_name"],
                "action": s["action"],
                "buy_price": s.get("ref_buy_price"),
                "target_sell_price": s.get("target_sell_price"),
                "stop_loss_price": s.get("stop_loss_price"),
                "reason": s["reason"],
            }
            for s in new_signals
        ]
        run.status = "success"
        await db.commit()
        logger.info(
            "规则策略评估完成: strategy=%s run_id=%s buy=%d sell=%d",
            strategy.name, run.id, buy_count, sell_count,
        )


# ----------------------------------------------------------------------
# 回测共用：规则逐日信号生成（纯函数，无前视——D-1 数据评估，D 日开盘成交）
# ----------------------------------------------------------------------
def gen_rule_signals(
    *,
    buy_conds: list[dict],
    sell_conds: list[dict],
    series_by_fid: dict[int, dict[str, dict[str, float]]],
    factor_codes: dict[int, str],
    pool_codes: list[str],
    trading_days: list[str],
    names: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """逐交易日生成规则信号：对交易日 D（下标 ≥1），用前一交易日 D-1 的因子值
    评估条件，信号 run_date 记为 D-1（回测引擎在 D 日开盘价执行该信号）。

    不模拟持仓状态：同票重复买入/无持仓卖出等情形由回测引擎按撮合语义跳过。
    卖出信号排在买入信号前（引擎每日执行顺序为先卖后买）。
    """
    names = names or {}
    signals: list[dict[str, Any]] = []

    def _details(conds: list[dict], code: str, day: str) -> Optional[str]:
        parts: list[str] = []
        for cond in conds:
            value = series_by_fid.get(cond["factor_id"], {}).get(code, {}).get(day)
            if value is None or not _compare(value, cond["op"], cond["value"]):
                return None
            fid = cond["factor_id"]
            parts.append(
                f"{factor_codes.get(fid, fid)} {_OP_SYMBOLS.get(cond['op'], cond['op'])} "
                f"{cond['value']}（实际 {value}，基准日 {day}）"
            )
        return "；".join(parts)

    for i in range(1, len(trading_days)):
        prev = trading_days[i - 1]
        for code in pool_codes:
            if sell_conds:
                detail = _details(sell_conds, code, prev)
                if detail is not None:
                    signals.append({
                        "stock_code": code,
                        "stock_name": names.get(code, "") or code,
                        "action": "sell",
                        "run_date": prev,
                        "reason": "规则卖出：" + detail,
                    })
            detail = _details(buy_conds, code, prev)
            if detail is not None:
                signals.append({
                    "stock_code": code,
                    "stock_name": names.get(code, "") or code,
                    "action": "buy",
                    "run_date": prev,
                    "reason": "规则买入：" + detail,
                })
    return signals
