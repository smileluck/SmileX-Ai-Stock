#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略参数寻优（sweep）服务：同步执行，不落库

数据准备复用 backtest_runner 的两条信号源路径（行情/信号/因子序列只取一次），
随后对参数网格笛卡尔积逐组调用 engine.run_replay 纯函数回放——引擎内部状态
（cash/positions/trades）均为函数局部变量，每组独立；唯一的外部可变共享是
warnings 列表（引擎会 append），每组传入副本隔离。
"""
import itertools
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode
from modules.backtest.schemas.backtest import (
    MAX_BACKTEST_YEARS,
    MAX_SWEEP_COMBINATIONS,
    BacktestSweepRequest,
    BacktestSweepResult,
    SweepParams,
    SweepResultItem,
)
from modules.backtest.services.backtest_runner import BacktestRunner
from modules.backtest.services.engine import run_replay
from modules.strategy.services.rule_executor import gen_rule_signals
from modules.strategy.services.strategy_service import StrategyService

logger = logging.getLogger(__name__)

# 响应绩效字段（从 engine result 摘取，warnings/win_count/loss_count 不下发）
_METRIC_KEYS = (
    "total_return_pct", "annual_return_pct", "max_drawdown_pct", "sharpe",
    "win_rate", "profit_factor", "trade_count", "final_equity",
)


class SweepService:
    """策略参数寻优服务类"""

    @staticmethod
    async def run_sweep(db: AsyncSession, req: BacktestSweepRequest) -> BacktestSweepResult:
        """同步执行参数寻优：数据准备一次，逐组纯函数回放，不落 business_backtest 表。

        校验：策略存在（11501）；日期口径同 /run；grid 三参数至少一个非空或存在
        buy_condition_scan；笛卡尔积 ≤27；prompt 型不允许买入条件扫描；rule 型
        condition_index 必须指向既有买入条件行。
        策略当前参数所在组合标 is_baseline；当前参数不在网格中时追加一组 baseline。
        """
        strategy = await StrategyService.get_by_id(db, req.strategy_id)

        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(req.end_date, "%Y-%m-%d").date()
        if start >= end:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg="回测开始日期必须早于结束日期",
            )
        if (end - start).days > MAX_BACKTEST_YEARS * 366:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg=f"回测区间不能超过 {MAX_BACKTEST_YEARS} 年",
            )

        is_rule = strategy.strategy_type == "rule"
        scan = req.buy_condition_scan
        grid_lists = [
            req.grid.stop_loss_pct, req.grid.take_profit_pct, req.grid.trailing_drawdown_pct,
        ]
        if not any(grid_lists) and scan is None:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg="参数网格为空：grid 三个参数至少给一个非空列表，或提供 buy_condition_scan",
            )
        if scan is not None and not is_rule:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg="prompt 型策略不支持 buy_condition_scan（买入条件扫描仅限规则型策略）",
            )
        if scan is not None:
            buy_conds_cfg = (strategy.rule_config or {}).get("buy_conditions") or []
            if scan.condition_index >= len(buy_conds_cfg):
                raise CustomError(
                    error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                    msg=f"condition_index {scan.condition_index} 超出买入条件行数 {len(buy_conds_cfg)}",
                )

        combos = 1
        for values in grid_lists:
            if values:
                combos *= len(values)
        if scan is not None:
            combos *= len(scan.values)
        if combos > MAX_SWEEP_COMBINATIONS:
            raise CustomError(
                error=CustomErrorCode.BACKTEST_INVALID_PARAMS,
                msg=f"参数组合数 {combos} 超过上限 {MAX_SWEEP_COMBINATIONS}，请缩小网格",
            )

        # ---- 数据准备一次（复用 runner 信号源路径） ----
        mode = "rule_daily_eval" if is_rule else "recorded_replay"
        rule_ctx = None
        if is_rule:
            rule_ctx = await BacktestRunner._rule_prepare(db, strategy, req.start_date, req.end_date)
            base_signals = None
            bars_by_code = rule_ctx["bars_by_code"]
            trading_days = rule_ctx["trading_days"]
            base_warnings = rule_ctx["warnings"]
        else:
            base_signals, bars_by_code, trading_days, base_warnings = (
                await BacktestRunner._recorded_signals(db, strategy, req.start_date, req.end_date)
            )

        def _f(v) -> float | None:
            return float(v) if v is not None else None

        base_stop = _f(strategy.stop_loss_pct)
        base_take = _f(strategy.take_profit_pct)
        base_trail = _f(strategy.trailing_drawdown_pct)
        scan_base_value = None
        scan_factor_id = None
        if scan is not None:
            cond = rule_ctx["buy_conds"][scan.condition_index]
            scan_base_value = float(cond["value"])
            scan_factor_id = cond["factor_id"]

        def _run_group(stop, take, trail, scan_value) -> dict:
            """单组参数回放；返回 (绩效 dict, 是否 baseline)"""
            signals = base_signals
            if is_rule:
                buy_conds = [dict(c) for c in rule_ctx["buy_conds"]]
                if scan is not None:
                    buy_conds[scan.condition_index]["value"] = scan_value
                signals = gen_rule_signals(
                    buy_conds=buy_conds,
                    sell_conds=rule_ctx["sell_conds"],
                    series_by_fid=rule_ctx["series_by_fid"],
                    factor_codes=rule_ctx["factor_codes"],
                    pool_codes=rule_ctx["pool_codes"],
                    trading_days=rule_ctx["trading_days"],
                    names=rule_ctx["names"],
                )
            replay = run_replay(
                signals=signals,
                bars_by_code=bars_by_code,
                trading_days=trading_days,
                initial_capital=float(req.initial_capital),
                max_positions=strategy.max_positions,
                slippage_pct=float(req.slippage_pct),
                slippage_model=req.slippage_model,
                commission_pct=float(req.commission_pct),
                stamp_tax_pct=float(req.stamp_tax_pct),
                stop_loss_pct=stop,
                take_profit_pct=take,
                trailing_drawdown_pct=trail,
                warnings=list(base_warnings),  # 引擎会 append，传副本隔离
            )
            is_baseline = (
                stop == base_stop and take == base_take and trail == base_trail
                and (scan is None or scan_value == scan_base_value)
            )
            return replay["result"], is_baseline

        # ---- 逐组回放 ----
        axes = [
            req.grid.stop_loss_pct or [None],
            req.grid.take_profit_pct or [None],
            req.grid.trailing_drawdown_pct or [None],
            scan.values if scan is not None else [None],
        ]
        results: list[SweepResultItem] = []
        has_baseline = False
        for grid_stop, grid_take, grid_trail, scan_value in itertools.product(*axes):
            stop = _f(grid_stop) if grid_stop is not None else base_stop
            take = _f(grid_take) if grid_take is not None else base_take
            trail = _f(grid_trail) if grid_trail is not None else base_trail
            metrics, is_baseline = _run_group(stop, take, trail, _f(scan_value))
            has_baseline = has_baseline or is_baseline
            results.append(SweepResultItem(
                params=SweepParams(
                    stop_loss_pct=stop,
                    take_profit_pct=take,
                    trailing_drawdown_pct=trail,
                    buy_condition=(
                        {"index": scan.condition_index, "factor_id": scan_factor_id,
                         "value": scan_value}
                        if scan is not None else None
                    ),
                ),
                **{k: metrics.get(k) for k in _METRIC_KEYS},
                is_baseline=is_baseline,
            ))

        # 当前参数不在网格中：追加一组 baseline
        if not has_baseline:
            metrics, _ = _run_group(base_stop, base_take, base_trail, scan_base_value)
            results.append(SweepResultItem(
                params=SweepParams(
                    stop_loss_pct=base_stop,
                    take_profit_pct=base_take,
                    trailing_drawdown_pct=base_trail,
                    buy_condition=(
                        {"index": scan.condition_index, "factor_id": scan_factor_id,
                         "value": scan_base_value}
                        if scan is not None else None
                    ),
                ),
                **{k: metrics.get(k) for k in _METRIC_KEYS},
                is_baseline=True,
            ))

        results.sort(
            key=lambda r: (r.total_return_pct is not None, r.total_return_pct or 0),
            reverse=True,
        )
        logger.info(
            "参数寻优完成: strategy=%s mode=%s total_runs=%d",
            strategy.name, mode, len(results),
        )
        return BacktestSweepResult(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            mode=mode,
            total_runs=len(results),
            results=results,
        )
