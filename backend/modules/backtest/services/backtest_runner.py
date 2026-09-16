#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回测后台执行器 —— 照搬 strategy_executor 的异步执行模式：
1. BacktestService.submit 创建 running 记录后立即返回
2. 本模块 spawn 在后台 asyncio 任务中执行回测（独立 session，只传 id 不传 ORM 实例）
3. 失败回写 failed + error_msg（裸 UPDATE，不访问过期属性）

执行内容：加载策略区间内真实 AI 信号 -> baostock 抓取交易日历与个股日线
-> 纯函数引擎逐日回放撮合 -> 落库成交明细/绩效汇总/净值曲线。
"""
import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.business.backtest import BusinessBacktest, BusinessBacktestTrade
from database.models.business.strategy import (
    BusinessAiStrategy,
    BusinessStrategyRun,
    BusinessStrategySignal,
)
from database.utils.timezone import timezone
from modules.backtest.services.engine import run_replay
from modules.backtest.services.market_data import fetch_market_data, is_supported_stock

logger = logging.getLogger(__name__)

# 后台回测整体超时（秒）：baostock 串行抓取多票日线可能较慢，兜底防悬挂
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

        # 1. 取该策略在区间内产生的全部真实 AI 信号（含 executed/skipped 等全部状态，
        #    关联 Run 排除已删除执行记录，按 run_date+id 升序回放）
        sig_result = await db.execute(
            select(BusinessStrategySignal)
            .join(
                BusinessStrategyRun,
                BusinessStrategyRun.id == BusinessStrategySignal.run_id,
            )
            .where(
                BusinessStrategySignal.strategy_id == strategy.id,
                BusinessStrategySignal.run_date >= backtest.start_date,
                BusinessStrategySignal.run_date <= backtest.end_date,
                BusinessStrategySignal.deleted_at.is_(None),
                BusinessStrategyRun.deleted_at.is_(None),
            )
            .order_by(BusinessStrategySignal.run_date, BusinessStrategySignal.id)
        )
        signal_rows = list(sig_result.scalars().all())

        warnings: list[str] = []
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

        # 2. 抓取行情：交易日历（上证指数）+ 个股日线（baostock 单连接串行）
        market = await fetch_market_data(
            sorted(stock_codes), backtest.start_date, backtest.end_date
        ) if stock_codes else {"trading_days": [], "bars": {}, "failed_codes": []}

        trading_days: list[str] = market["trading_days"]
        if not trading_days:
            raise RuntimeError(
                f"回测区间 {backtest.start_date}~{backtest.end_date} 内无交易日（交易日历为空）"
            )
        for code in market["failed_codes"]:
            warnings.append(f"股票 {code} 区间内无行情数据，其信号将无法成交")

        # 单次回测内内存缓存：code -> {date: bar}
        bars_by_code = {
            code: {b["date"]: b for b in bars}
            for code, bars in market["bars"].items()
        }

        # 3. 纯函数逐日回放
        replay = run_replay(
            signals=signals,
            bars_by_code=bars_by_code,
            trading_days=trading_days,
            initial_capital=float(backtest.initial_capital),
            max_positions=strategy.max_positions,
            slippage_pct=float(backtest.slippage_pct),
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
