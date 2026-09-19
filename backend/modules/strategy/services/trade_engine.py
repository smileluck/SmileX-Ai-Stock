#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
模拟交易引擎 —— 由调度任务每分钟触发一次 tick：
1. 恢复僵死执行记录（running 超时，进程重启/异常中断兜底）
2. 过期滞留待执行信号（收盘后作废 run_date 早于今日的信号）
3. 交易时段内：按新浪实时价执行待执行买卖信号（先卖后买再调整），
   并刷新全部持仓最新价/浮盈、触发止损/止盈/目标价自动平仓

信号与持仓的行情只做一次批量拉取。
"""
import logging
from datetime import datetime, time as dt_time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.business.strategy import (
    BusinessAiStrategy,
    BusinessStrategyRun,
    BusinessStrategyPosition,
    BusinessStrategySignal,
)
from database.utils.timezone import timezone
from modules.stock.services.trading_calendar import is_trading_day
from modules.strategy.services.position_service import (
    PositionService,
    close_position_atomic,
    is_t1_locked,
)
from modules.strategy.services.quote_helper import fetch_latest_quotes

logger = logging.getLogger(__name__)

# 僵死 running 记录判定阈值（分析任务自带 ANALYSIS_TIMEOUT 兜底，
# 超过该时长仍是 running 必为进程重启或异常中断）
STALE_RUN_MINUTES = 15

# 僵死 running 回测判定阈值（回测自带 BACKTEST_TIMEOUT=900s 兜底，20 分钟留余量）
BACKTEST_STALE_MINUTES = 20

# 信号过期时点：收盘后 15:05，作废 run_date 早于今日的滞留信号
# （当日盘后分析产生的信号 run_date=今日，仍保留至下一交易日执行）
SIGNAL_EXPIRE_TIME = dt_time(15, 5)

# 连续竞价时段（信号执行与持仓跟踪窗口，周一至周五）
_TRADING_WINDOWS: tuple[tuple[dt_time, dt_time], ...] = (
    (dt_time(9, 30), dt_time(11, 30)),
    (dt_time(13, 0), dt_time(15, 0)),
)

# 信号执行顺序：先卖（腾出仓位）后买再调整
_ACTION_ORDER = {"sell": 0, "buy": 1, "adjust": 2}

# 买入信号参考价与实时价允许的最大偏差（%）：超出视为 AI 参考价过期/失真，拒单
# （历史数据：67 笔已执行买入平均偏差 29.3%，最大 953%，买入远高于 AI 假设价位）
REF_PRICE_MAX_DEVIATION_PCT = 3.0

# 涨停保护触发的 AI 复核节流窗口（分钟）：同策略窗口内已有复核运行时不重复提交
REVIEW_THROTTLE_MINUTES = 30

# 行情降级告警：请求了行情却连续 N 个 tick 拿到空 dict 时 logger.error 结构化告警
QUOTE_EMPTY_ALERT_THRESHOLD = 5

# 模块级连续空行情 tick 计数（多 worker 各自计数，告警按进程粒度）
_empty_quote_ticks = 0


async def _in_trading_hours(now: datetime) -> bool:
    """是否处于连续竞价时段（交易日历感知：法定节假日休市，数据源故障降级周一至周五）"""
    if not await is_trading_day(now.date()):
        return False
    current = now.time()
    return any(start <= current <= end for start, end in _TRADING_WINDOWS)


def _bump_run_delta(run_delta: dict[int, dict[str, int]], run_id: int, *, opened: int = 0, closed: int = 0) -> None:
    """累计来源 Run 的新建仓/平仓数"""
    delta = run_delta.setdefault(run_id, {"opened": 0, "closed": 0})
    delta["opened"] += opened
    delta["closed"] += closed


def _sanitize_price_levels(
    price: float,
    strategy: BusinessAiStrategy,
    stop_loss_price: float | None,
    target_sell_price: float | None,
) -> tuple[float | None, float | None]:
    """价格位 sanity 修正：AI 给的止损价可能高于买价（如按"支撑位"给出）、
    目标价可能低于买价，会导致建仓即触发止损/达标平仓。
    无效价格位按策略配置的止损/止盈百分比重算。
    """
    stop = stop_loss_price
    if stop is None or stop >= price:
        pct = float(strategy.stop_loss_pct) if strategy.stop_loss_pct is not None else None
        stop = round(price * (1 - pct / 100), 4) if pct is not None else None
    target = target_sell_price
    if target is None or target <= price:
        pct = float(strategy.take_profit_pct) if strategy.take_profit_pct is not None else None
        target = round(price * (1 + pct / 100), 4) if pct is not None else None
    return stop, target


class TradeEngine:
    """每分钟模拟交易引擎：执行待执行信号 + 持仓跟踪，共用一次行情拉取"""

    @staticmethod
    async def execute_tick(db: AsyncSession) -> dict:
        now = timezone.now()
        total: dict = {
            "expired_stale_runs": 0, "expired_signals": 0,
            "executed": 0, "skipped": 0, "opened": 0, "closed": 0,
        }

        # ---- 1. 僵死 running 记录恢复 ----
        stale_before = now - timedelta(minutes=STALE_RUN_MINUTES)
        result = await db.execute(
            update(BusinessStrategyRun)
            .where(
                BusinessStrategyRun.status == "running",
                BusinessStrategyRun.created_at < stale_before,
                BusinessStrategyRun.deleted_at.is_(None),
            )
            .values(
                status="failed",
                error_msg=f"执行超时（超过 {STALE_RUN_MINUTES} 分钟未完成，疑似进程重启或异常中断）",
            )
            .execution_options(synchronize_session=False)
        )
        total["expired_stale_runs"] = result.rowcount or 0

        # ---- 1b. 僵死 running 回测恢复（同样照 STALE_RUN_MINUTES 模式） ----
        from database.models.business.backtest import BusinessBacktest

        stale_bt_before = now - timedelta(minutes=BACKTEST_STALE_MINUTES)
        result = await db.execute(
            update(BusinessBacktest)
            .where(
                BusinessBacktest.status == "running",
                func.coalesce(BusinessBacktest.started_at, BusinessBacktest.created_at) < stale_bt_before,
                BusinessBacktest.deleted_at.is_(None),
            )
            .values(
                status="failed",
                error_msg=f"执行超时（超过 {BACKTEST_STALE_MINUTES} 分钟未完成，疑似进程重启）",
                finished_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        total["expired_stale_backtests"] = result.rowcount or 0

        # ---- 2. 信号过期：收盘后作废昨日及更早的滞留信号 ----
        if now.time() >= SIGNAL_EXPIRE_TIME:
            today = now.strftime("%Y-%m-%d")
            result = await db.execute(
                update(BusinessStrategySignal)
                .where(
                    BusinessStrategySignal.status == "pending",
                    BusinessStrategySignal.run_date < today,
                    BusinessStrategySignal.deleted_at.is_(None),
                )
                .values(status="expired", result_msg="超过有效期（次日收盘后作废）")
                .execution_options(synchronize_session=False)
            )
            total["expired_signals"] = result.rowcount or 0

        # 维护性变更先落库（即使后续交易步骤异常也不回滚）
        if total["expired_stale_runs"] or total["expired_signals"] or total["expired_stale_backtests"]:
            await db.commit()

        # ---- 3. 非交易时段：仅做维护动作 ----
        if not await _in_trading_hours(now):
            total.update({"skipped_tick": True, "reason": "非交易时段"})
            return total

        # ---- 4. 启用策略与待执行信号 ----
        str_result = await db.execute(
            select(BusinessAiStrategy).where(
                BusinessAiStrategy.status == True,  # noqa: E712
                BusinessAiStrategy.deleted_at.is_(None),
            )
        )
        strategies = {s.id: s for s in str_result.scalars().all()}

        sig_result = await db.execute(
            select(BusinessStrategySignal).where(
                BusinessStrategySignal.status == "pending",
                BusinessStrategySignal.deleted_at.is_(None),
            )
        )
        pending_signals = list(sig_result.scalars().all())

        # 策略已停用/删除：信号作废（条件 UPDATE 保持 pending→expired 原子，
        # 已被并发执行者认领的信号不受影响）
        alive_signals = []
        for sig in pending_signals:
            if sig.strategy_id in strategies:
                alive_signals.append(sig)
                continue
            result = await db.execute(
                update(BusinessStrategySignal)
                .where(
                    BusinessStrategySignal.id == sig.id,
                    BusinessStrategySignal.status == "pending",
                    BusinessStrategySignal.deleted_at.is_(None),
                )
                .values(status="expired", result_msg="策略已停用或删除")
                .execution_options(synchronize_session=False)
            )
            if (result.rowcount or 0) == 1:
                total["expired_signals"] += 1
        pending_signals = alive_signals

        # ---- 5. 全部持仓 + 一次批量行情（信号股 ∪ 持仓股） ----
        pos_result = await db.execute(
            select(BusinessStrategyPosition).where(
                BusinessStrategyPosition.status == "holding",
                BusinessStrategyPosition.deleted_at.is_(None),
            )
        )
        positions = list(pos_result.scalars().all())

        codes = {s.stock_code for s in pending_signals} | {p.stock_code for p in positions}
        quotes = await fetch_latest_quotes(list(codes)) if codes else {}
        # 行情降级告警：请求了行情却连续拿到空 dict（接口故障时风控整体静默失效，
        # 须以结构化 ERROR 暴露，参照 main.py startup_degraded 风格）
        global _empty_quote_ticks
        if codes and not quotes:
            _empty_quote_ticks += 1
            if _empty_quote_ticks >= QUOTE_EMPTY_ALERT_THRESHOLD:
                logger.error(
                    "实时行情连续 %d 个 tick 为空，信号执行与风控降级运行（请求 %d 只）",
                    _empty_quote_ticks, len(codes),
                    extra={
                        "event": "quote_degraded",
                        "component": "trade_engine",
                        "consecutive_ticks": _empty_quote_ticks,
                        "codes": len(codes),
                    },
                )
        elif quotes:
            if _empty_quote_ticks >= QUOTE_EMPTY_ALERT_THRESHOLD:
                logger.info(
                    "实时行情已恢复（此前连续 %d 个 tick 为空）",
                    _empty_quote_ticks,
                    extra={"event": "quote_recovered", "component": "trade_engine"},
                )
            _empty_quote_ticks = 0
        prices = {code: q["price"] for code, q in quotes.items()}
        changes = {code: q["change_pct"] for code, q in quotes.items() if q["change_pct"] is not None}

        # strategy_id -> {stock_code: position}
        holding_map: dict[int, dict[str, BusinessStrategyPosition]] = {}
        for pos in positions:
            holding_map.setdefault(pos.strategy_id, {})[pos.stock_code] = pos

        # ---- 6. 执行信号（先卖后买再调整；停牌/缺价保持 pending 下一分钟重试） ----
        pending_signals.sort(key=lambda s: _ACTION_ORDER.get(s.action, 9))
        run_delta: dict[int, dict[str, int]] = {}

        for sig in pending_signals:
            strategy = strategies[sig.strategy_id]
            pos = holding_map.get(sig.strategy_id, {}).get(sig.stock_code)
            price = prices.get(sig.stock_code)

            if sig.action == "sell":
                if pos is None:
                    if await TradeEngine._claim_signal(
                        db, sig, status="skipped", result_msg="无持仓可卖"
                    ):
                        total["skipped"] += 1
                    continue
                if not price:
                    continue
                # T+1：当日买入的持仓不可卖出，信号保持待执行至下一交易日
                if is_t1_locked(pos.buy_time, now):
                    continue
                # 先条件 UPDATE 认领信号再平仓：认领失败说明已被并发执行者处理或已作废
                if not await TradeEngine._claim_signal(
                    db, sig, status="executed", executed_at=now, executed_price=price,
                    result_msg=f"按实时价 {price} 平仓",
                ):
                    continue
                # 除零守卫：buy_price 脏数据（<=0）时不计算收益率
                buy_price = float(pos.buy_price)
                return_rate = (
                    round((price - buy_price) / buy_price * 100, 4) if buy_price > 0 else None
                )
                # 持仓同样走条件 UPDATE（holding→closed），并发平仓只有一个生效
                if await close_position_atomic(
                    db, pos, price=price, now=now,
                    sell_reason="ai_signal", return_rate=return_rate,
                ):
                    holding_map[sig.strategy_id].pop(sig.stock_code, None)
                    _bump_run_delta(run_delta, sig.run_id, closed=1)
                    total["closed"] += 1
                    total["executed"] += 1
                else:
                    # 信号已认领但持仓被并发平仓：不计 executed（信号未真正成交），
                    # 并移出 holding_map，避免同 tick 后续同股信号读到 stale 持仓
                    logger.warning(
                        "信号已认领但持仓已被并发平仓: signal_id=%s position_id=%s",
                        sig.id, pos.id,
                    )
                    holding_map[sig.strategy_id].pop(sig.stock_code, None)
                continue

            if sig.action == "buy":
                if pos is not None:
                    if await TradeEngine._claim_signal(
                        db, sig, status="skipped", result_msg="已持仓，跳过重复买入"
                    ):
                        total["skipped"] += 1
                    continue
                if len(holding_map.get(sig.strategy_id, {})) >= strategy.max_positions:
                    if await TradeEngine._claim_signal(
                        db, sig, status="skipped",
                        result_msg=f"已达最大持仓数 {strategy.max_positions}",
                    ):
                        total["skipped"] += 1
                    continue
                if not price:
                    continue
                # 参考价偏差守卫：实时价偏离 AI 参考价超阈值时拒单
                # （说明 AI 分析时看到的价格已严重过期，止损/目标位均不可信）。
                # 口径差异：rule 策略参考价锚定 D-1 收盘价（rule_executor），
                # 高开/低开超阈值是正常行情而非 LLM 价格失真，故 rule 策略跳过该守卫。
                if sig.ref_buy_price and strategy.strategy_type != "rule":
                    ref = float(sig.ref_buy_price)
                    if ref > 0:
                        deviation_pct = abs(price - ref) / ref * 100
                        if deviation_pct > REF_PRICE_MAX_DEVIATION_PCT:
                            if await TradeEngine._claim_signal(
                                db, sig, status="skipped",
                                result_msg=(
                                    f"实时价 {price} 与参考价 {ref} 偏差 {deviation_pct:.1f}% "
                                    f"(>{REF_PRICE_MAX_DEVIATION_PCT}%)，拒单"
                                ),
                            ):
                                total["skipped"] += 1
                            continue
                # 先条件 UPDATE 认领信号再建仓：并发执行者只有一个认领成功，杜绝重复建仓
                if not await TradeEngine._claim_signal(
                    db, sig, status="executed", executed_at=now, executed_price=price,
                    result_msg=f"按实时价 {price} 建仓",
                ):
                    continue
                # AI 价格位校验修正：止损必须低于买价、目标必须高于买价
                stop_loss, target_sell = _sanitize_price_levels(
                    price, strategy, sig.stop_loss_price, sig.target_sell_price
                )
                pos = BusinessStrategyPosition(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    stock_code=sig.stock_code,
                    stock_name=sig.stock_name or sig.stock_code,
                    buy_price=price,
                    buy_time=now,
                    buy_reason=sig.reason,
                    run_id=sig.run_id,
                    target_sell_price=target_sell,
                    stop_loss_price=stop_loss,
                    trailing_drawdown_pct=strategy.trailing_drawdown_pct,
                    peak_price=price,
                    status="holding",
                    latest_price=price,
                    floating_pnl_pct=0.0,
                    tracked_at=now,
                )
                db.add(pos)
                holding_map.setdefault(sig.strategy_id, {})[sig.stock_code] = pos
                _bump_run_delta(run_delta, sig.run_id, opened=1)
                total["executed"] += 1
                total["opened"] += 1
                continue

            # adjust：更新预估卖点/止损价（方向校验，防立即触发止损/达标）
            if pos is None:
                if await TradeEngine._claim_signal(
                    db, sig, status="skipped", result_msg="无持仓可调整"
                ):
                    total["skipped"] += 1
                continue
            if not price:
                continue
            new_target = None
            new_stop = None
            notes: list[str] = []
            if sig.target_sell_price:
                if sig.target_sell_price > price:
                    new_target = sig.target_sell_price
                else:
                    notes.append("目标价不高于现价已忽略")
            if sig.stop_loss_price:
                # 止损价只允许上移（且须低于现价）：防 AI 无限放宽止损导致风控失效
                if (sig.stop_loss_price < price
                        and sig.stop_loss_price > float(pos.stop_loss_price or 0)):
                    new_stop = sig.stop_loss_price
                else:
                    notes.append("止损价未上移已忽略")
            if not await TradeEngine._claim_signal(
                db, sig, status="executed", executed_at=now, executed_price=price,
                result_msg="；".join(notes) or "已调整卖点/止损价",
            ):
                continue
            # 持仓字段更新也走条件 UPDATE（WHERE status='holding'）：
            # 持仓被并发平仓时 rowcount==0，跳过内存赋值防覆盖并发平仓结果
            pos_updates = {}
            if new_target is not None:
                pos_updates["target_sell_price"] = new_target
            if new_stop is not None:
                pos_updates["stop_loss_price"] = new_stop
            if pos_updates:
                result = await db.execute(
                    update(BusinessStrategyPosition)
                    .where(
                        BusinessStrategyPosition.id == pos.id,
                        BusinessStrategyPosition.status == "holding",
                        BusinessStrategyPosition.deleted_at.is_(None),
                    )
                    .values(**pos_updates)
                    .execution_options(synchronize_session=False)
                )
                if (result.rowcount or 0) == 1:
                    for field, value in pos_updates.items():
                        setattr(pos, field, value)
                else:
                    logger.info(
                        "adjust 时持仓已被并发平仓，跳过赋值: position_id=%s", pos.id
                    )
                    holding_map[sig.strategy_id].pop(sig.stock_code, None)
            total["executed"] += 1

        # ---- 7. 来源 Run 计数累加（新建仓/平仓数） ----
        for run_id, delta in run_delta.items():
            values = {}
            if delta["opened"]:
                values["opened_count"] = BusinessStrategyRun.opened_count + delta["opened"]
            if delta["closed"]:
                values["closed_count"] = BusinessStrategyRun.closed_count + delta["closed"]
            if values:
                await db.execute(
                    update(BusinessStrategyRun)
                    .where(BusinessStrategyRun.id == run_id)
                    .values(**values)
                    .execution_options(synchronize_session=False)
                )

        # ---- 8. 持仓跟踪：刷新价格/浮盈 + 止损/止盈/目标价自动平仓（复用已拉行情） ----
        track_stats = await PositionService.track_positions(db, prices=prices, changes=changes)
        total["tracked"] = track_stats.get("tracked", 0)
        total["track_closed"] = track_stats.get("closed", 0)
        total["limit_protected"] = track_stats.get("limit_protected", 0)

        # ---- 9. 涨停保护触发的 AI 即时复核（不受时段窗口限制，30 分钟节流） ----
        total["review_submitted"] = await TradeEngine._submit_limit_reviews(
            db, strategies, track_stats.get("review_strategy_ids") or set(), now
        )

        await db.commit()
        logger.info(
            "交易引擎 tick 完成: executed=%d skipped=%d opened=%d closed=%d tracked=%d expired_signals=%d",
            total["executed"], total["skipped"], total["opened"], total["closed"],
            total["tracked"], total["expired_signals"],
        )
        return total

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    async def _submit_limit_reviews(
        db: AsyncSession,
        strategies: dict[int, BusinessAiStrategy],
        strategy_ids: set[int],
        now: datetime,
    ) -> int:
        """涨停保护触发的 AI 即时复核：为对应策略异步提交一轮持仓复核分析。

        不受策略执行时段窗口限制（持仓风险管理优先），30 分钟节流防重复提交，
        并发守卫由 submit_run 的 running 检查兜底。
        """
        if not strategy_ids:
            return 0
        # 函数内延迟导入防循环依赖；走 StrategyService.submit_run 按 strategy_type
        # 分流（rule 策略复核走规则评估而非 LLM），并发守卫由执行器统一兜底
        from modules.strategy.services.strategy_service import StrategyService

        throttle_before = now - timedelta(minutes=REVIEW_THROTTLE_MINUTES)
        submitted = 0
        for sid in strategy_ids:
            strategy = strategies.get(sid)
            if strategy is None:
                continue  # 策略已停用/删除，交给持仓跟踪的机械规则兜底
            dup = await db.execute(
                select(BusinessStrategyRun.id).where(
                    BusinessStrategyRun.strategy_id == sid,
                    BusinessStrategyRun.run_period == "review",
                    BusinessStrategyRun.created_at >= throttle_before,
                    BusinessStrategyRun.deleted_at.is_(None),
                ).limit(1)
            )
            if dup.scalar_one_or_none() is not None:
                continue
            try:
                await StrategyService.submit_run(
                    db, sid, run_period="review", trigger_type="review"
                )
                submitted += 1
            except Exception:  # noqa: BLE001  并发守卫等业务异常不阻断 tick
                logger.warning("涨停复核提交失败: strategy=%s", strategy.name, exc_info=True)
        if submitted:
            logger.info("涨停保护触发 AI 复核: submitted=%d strategies=%s",
                        submitted, sorted(strategy_ids))
        return submitted

    @staticmethod
    async def _claim_signal(
        db: AsyncSession,
        sig: BusinessStrategySignal,
        **values,
    ) -> bool:
        """条件 UPDATE 认领信号（pending→终态原子化）：rowcount==1 表示认领成功。

        认领失败（rowcount==0：已被并发执行者处理或被新一轮分析作废）时调用方必须跳过。
        synchronize_session=False 不会同步内存 ORM 对象，认领成功后手动同步字段，
        保证依赖该对象的后续逻辑看到一致状态。
        """
        result = await db.execute(
            update(BusinessStrategySignal)
            .where(
                BusinessStrategySignal.id == sig.id,
                BusinessStrategySignal.status == "pending",
                BusinessStrategySignal.deleted_at.is_(None),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if (result.rowcount or 0) != 1:
            return False
        for field, value in values.items():
            setattr(sig, field, value)
        return True
