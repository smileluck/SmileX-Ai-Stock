#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测后台执行器 —— 照搬 strategy_executor 的异步执行模式：
1. BacktestService.submit 创建 running 记录后立即返回
2. 本模块 spawn 在后台 asyncio 任务中执行回测（独立 session，只传 id 不传 ORM 实例）
3. 失败回写 failed + error_msg（裸 UPDATE，不访问过期属性）

执行内容：按策略类型分流信号源——
- prompt 型：加载策略区间内已记录的真实 AI 信号（recorded_replay）
- rule 型：按 rule_config 逐交易日评估因子条件自产信号（rule_daily_eval，
  信号由 ≤D-1 数据生成，D 日开盘成交，严格无未来函数）
随后抓取交易日历与个股日线（akshare-东财主源、baostock 降级）-> 纯函数引擎逐日回放撮合
-> 落库成交明细/绩效汇总/净值曲线。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode
from database.models.business.backtest import BusinessBacktest, BusinessBacktestTrade
from database.models.business.factor import BusinessFactor
from database.models.business.strategy import (
    BusinessAiStrategy,
    BusinessStrategyRun,
    BusinessStrategySignal,
)
from database.utils.timezone import timezone
from modules.backtest.services.engine import run_replay
from modules.backtest.services.market_data import fetch_market_data, is_supported_stock
from modules.factor.services.factor_calc import _latest_stock_names
from modules.factor.services.formula import calc_factor_series
from modules.strategy.services.rule_executor import RULE_LOOKBACK, gen_rule_signals

logger = logging.getLogger(__name__)

# 后台回测整体超时（秒）：行情串行抓取多票日线可能较慢，兜底防悬挂
BACKTEST_TIMEOUT = 900

# 后台任务强引用集合（防止 asyncio.Task 被 GC），完成后自动移除
_BACKGROUND_TASKS: set[asyncio.Task] = set()


class BacktestRunner:
    """回测后台执行器"""

    @staticmethod
    def spawn(backtest_id: int) -> None:
        """启动后台回测任务（不等待完成）"""
        task = asyncio.create_task(BacktestRunner._execute(backtest_id))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

    # ------------------------------------------------------------------
    # 后台执行
    # ------------------------------------------------------------------
    @staticmethod
    async def _execute(backtest_id: int) -> None:
        """后台执行入口：独立 session + 整体超时兜底，任何异常都回写失败状态"""
        from database.db_manager import get_session

        async for db in get_session():
            try:
                await asyncio.wait_for(
                    BacktestRunner._run(db, backtest_id), timeout=BACKTEST_TIMEOUT
                )
            except Exception as exc:  # noqa: BLE001  含 TimeoutError
                if isinstance(exc, asyncio.TimeoutError):
                    err_text = f"回测执行超时（超过 {BACKTEST_TIMEOUT} 秒）"
                else:
                    # 项目异常（CustomError 等）消息在 .msg 属性，str(exc) 可能为空
                    err_text = str(getattr(exc, "msg", None) or exc)
                logger.warning("回测执行失败: backtest_id=%s error=%s", backtest_id, err_text)
                try:
                    await db.rollback()
                    await db.execute(
                        update(BusinessBacktest)
                        .where(BusinessBacktest.id == backtest_id)
                        .values(
                            status="failed",
                            error_msg=err_text[:1000],
                            finished_at=timezone.now(),
                        )
                        .execution_options(synchronize_session=False)
                    )
                    await db.commit()
                except Exception:  # noqa: BLE001
                    logger.exception("回写失败回测记录异常: backtest_id=%s", backtest_id)

    @staticmethod
    async def _run(db: AsyncSession, backtest_id: int) -> None:
        """回测主体：取信号 -> 抓行情 -> 逐日回放 -> 落库"""
        result = await db.execute(
            select(BusinessBacktest).where(BusinessBacktest.id == backtest_id)
        )
        backtest = result.scalar_one_or_none()
        if backtest is None or backtest.deleted_at is not None:
            logger.warning("回测记录不存在，放弃执行: backtest_id=%s", backtest_id)
            return

        str_result = await db.execute(
            select(BusinessAiStrategy).where(
                BusinessAiStrategy.id == backtest.strategy_id,
                BusinessAiStrategy.deleted_at.is_(None),
            )
        )
        strategy = str_result.scalar_one_or_none()
        if strategy is None:
            backtest.status = "failed"
            backtest.error_msg = "策略不存在或已删除"
            backtest.finished_at = timezone.now()
            await db.commit()
            return

        backtest.started_at = timezone.now()
        await db.commit()

        if strategy.strategy_type == "rule":
            ctx = await BacktestRunner._rule_prepare(
                db, strategy, backtest.start_date, backtest.end_date
            )
            signals = gen_rule_signals(
                buy_conds=ctx["buy_conds"],
                sell_conds=ctx["sell_conds"],
                series_by_fid=ctx["series_by_fid"],
                factor_codes=ctx["factor_codes"],
                pool_codes=ctx["pool_codes"],
                trading_days=ctx["trading_days"],
                names=ctx["names"],
            )
            bars_by_code = ctx["bars_by_code"]
            trading_days = ctx["trading_days"]
            warnings = ctx["warnings"]
        else:
            signals, bars_by_code, trading_days, warnings = await BacktestRunner._recorded_signals(
                db, strategy, backtest.start_date, backtest.end_date
            )

        # 3. 纯函数逐日回放
        replay = run_replay(
            signals=signals,
            bars_by_code=bars_by_code,
            trading_days=trading_days,
            initial_capital=float(backtest.initial_capital),
            max_positions=strategy.max_positions,
            slippage_pct=float(backtest.slippage_pct),
            slippage_model=backtest.slippage_model,
            commission_pct=float(backtest.commission_pct),
            stamp_tax_pct=float(backtest.stamp_tax_pct),
            stop_loss_pct=float(strategy.stop_loss_pct) if strategy.stop_loss_pct is not None else None,
            take_profit_pct=float(strategy.take_profit_pct) if strategy.take_profit_pct is not None else None,
            trailing_drawdown_pct=(
                float(strategy.trailing_drawdown_pct)
                if strategy.trailing_drawdown_pct is not None else None
            ),
            warnings=warnings,
        )

        # 4. 落库：成交明细 + 绩效汇总 + 净值曲线
        for t in replay["trades"]:
            db.add(BusinessBacktestTrade(backtest_id=backtest.id, **t))

        backtest.result = replay["result"]
        backtest.equity_curve = replay["equity_curve"]
        backtest.status = "success"
        backtest.finished_at = timezone.now()
        await db.commit()
        logger.info(
            "回测完成: backtest_id=%s trades=%d total_return=%s",
            backtest_id, len(replay["trades"]),
            replay["result"].get("total_return_pct"),
        )

    # ------------------------------------------------------------------
    # 信号源：prompt 型回放已记录信号（recorded_replay）
    # ------------------------------------------------------------------
    @staticmethod
    async def _recorded_signals(
        db: AsyncSession, strategy: BusinessAiStrategy, start_date: str, end_date: str
    ) -> tuple[list[dict], dict, list[str], list[str]]:
        """取该策略在区间内产生的全部真实 AI 信号（含 executed/skipped 等全部状态，
        关联 Run 排除已删除执行记录，按 run_date+id 升序回放）"""
        sig_result = await db.execute(
            select(BusinessStrategySignal)
            .join(
                BusinessStrategyRun,
                BusinessStrategyRun.id == BusinessStrategySignal.run_id,
            )
            .where(
                BusinessStrategySignal.strategy_id == strategy.id,
                BusinessStrategySignal.run_date >= start_date,
                BusinessStrategySignal.run_date <= end_date,
                BusinessStrategySignal.deleted_at.is_(None),
                BusinessStrategyRun.deleted_at.is_(None),
            )
            .order_by(BusinessStrategySignal.run_date, BusinessStrategySignal.id)
        )
        signal_rows = list(sig_result.scalars().all())

        warnings: list[str] = [
            "回测模式：recorded_replay（回放区间内已记录的真实 AI 信号）"
        ]
        signals: list[dict] = []
        unsupported: set[str] = set()
        stock_codes: set[str] = set()
        for row in signal_rows:
            code = row.stock_code
            if not is_supported_stock(code):
                if code not in unsupported:
                    unsupported.add(code)
                    warnings.append(f"股票 {code}（{row.stock_name}）为北交所等 baostock 不支持标的，已跳过")
                continue
            stock_codes.add(code)
            signals.append({
                "stock_code": code,
                "stock_name": row.stock_name,
                "action": row.action,
                "run_date": row.run_date,
                "target_sell_price": float(row.target_sell_price) if row.target_sell_price is not None else None,
                "stop_loss_price": float(row.stop_loss_price) if row.stop_loss_price is not None else None,
                "reason": row.reason,
            })

        # 抓取行情：交易日历（上证指数）+ 个股日线（akshare 主源、baostock 降级）
        market = await fetch_market_data(
            sorted(stock_codes), start_date, end_date
        ) if stock_codes else {"trading_days": [], "bars": {}, "failed_codes": []}

        trading_days: list[str] = market["trading_days"]
        if not trading_days:
            raise RuntimeError(
                f"回测区间 {start_date}~{end_date} 内无交易日（交易日历为空）"
            )
        for code in market["failed_codes"]:
            warnings.append(f"股票 {code} 区间内无行情数据，其信号将无法成交")

        # 单次回测内内存缓存：code -> {date: bar}
        bars_by_code = {
            code: {b["date"]: b for b in bars}
            for code, bars in market["bars"].items()
        }
        return signals, bars_by_code, trading_days, warnings

    # ------------------------------------------------------------------
    # 信号源：rule 型逐日评估因子条件自产信号（rule_daily_eval，无前视）
    # ------------------------------------------------------------------
    @staticmethod
    async def _rule_prepare(
        db: AsyncSession, strategy: BusinessAiStrategy, start_date: str, end_date: str
    ) -> dict:
        """rule 型回测数据准备（行情/因子序列/条件快照，供信号生成复用）。

        每票 bars 一次载入内存，因子全序列一次算好（RANK 按交易日逐日截面）；
        返回上下文字典：bars_by_code/trading_days/warnings/series_by_fid/
        factor_codes/pool_codes/names/buy_conds/sell_conds——信号生成见
        gen_rule_signals（条件 value 可被 sweep 等场景覆盖后重新生成信号）。"""
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

        warnings: list[str] = [
            "回测模式：rule_daily_eval（规则逐日评估：信号由 ≤D-1 数据生成，D 日开盘成交）"
        ]
        supported: list[str] = []
        for code in dict.fromkeys(pool_codes):
            if is_supported_stock(code):
                supported.append(code)
            else:
                warnings.append(f"股票 {code} 为北交所等 baostock 不支持标的，已跳过")
        if not supported:
            raise CustomError(
                error=CustomErrorCode.STRATEGY_RULE_NO_POOL,
                msg="股票池为空或不包含可支持的 A 股代码",
            )

        # 因子校验（保存时已校验，此处防因子事后被删/停用）
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

        # 行情窗口前置 lookback×2 自然日（供窗口函数预热）；交易日序列截取回测区间
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        fetch_start = (start - timedelta(days=RULE_LOOKBACK * 2)).strftime("%Y-%m-%d")
        market = await fetch_market_data(supported, fetch_start, end_date)
        trading_days = [
            d for d in market["trading_days"]
            if start_date <= d <= end_date
        ]
        if not trading_days:
            raise RuntimeError(
                f"回测区间 {start_date}~{end_date} 内无交易日（交易日历为空）"
            )
        for code in market["failed_codes"]:
            warnings.append(f"股票 {code} 区间内无行情数据，其信号将无法成交")

        bars_list: dict[str, list[dict]] = market["bars"]
        bars_by_code = {
            code: {b["date"]: b for b in bars}
            for code, bars in bars_list.items()
        }

        series_by_fid: dict[int, dict[str, dict[str, float]]] = {}
        for fid, factor in factors.items():
            series, calc_warnings = calc_factor_series(factor.formula, bars_list)
            warnings.extend(calc_warnings)
            series_by_fid[fid] = series

        names = await _latest_stock_names(db, supported)
        return {
            "bars_by_code": bars_by_code,
            "trading_days": trading_days,
            "warnings": warnings,
            "series_by_fid": series_by_fid,
            "factor_codes": factor_codes,
            "pool_codes": supported,
            "names": names,
            "buy_conds": buy_conds,
            "sell_conds": sell_conds,
        }
