"""清理非交易日误执行的交易（交易日历长假 fail-open 历史遗留）。

背景：交易日历陈旧降级曾以「上一自然工作日」为锚，长假第 2 个工作日起会误判为
交易日（如 2026-10-02 国庆休市但判为开市），交易引擎在休市日按上一交易日陈旧
收盘价执行模拟买卖。修复后（FQGate 权威日历 + 行情新鲜度校验）用本脚本清理存量。

清理口径：
- A 类：买入时间落在非交易日的持仓（含已平仓）——整笔为误成交，
  --apply 时软删持仓、对应 executed 买入信号置 expired、修正 run 的 opened_count；
- B 类：买入日合法但卖出时间落在非交易日的持仓——只报告不自动处理，人工核对；
- C 类：非交易日生成的 pending 信号——依据的是休市日陈旧快照，且按交易日口径的
  有效期会活到下一交易日开盘被误执行，--apply 时置 expired。

用法：
    cd backend && ENVIR=dev .venv/bin/python -m scripts.cleanup_nontrading_day_trades
    cd backend && ENVIR=dev .venv/bin/python -m scripts.cleanup_nontrading_day_trades --apply
"""
import argparse
import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update

from core.fqgate import calendar as fq_calendar
from database.db_manager import init_pool, close_pool
from database.manager.async_manager import get_session
from database.models.business.strategy import (
    BusinessStrategyPosition,
    BusinessStrategyRun,
    BusinessStrategySignal,
)
from database.utils.timezone import timezone
from modules.stock.services import _fqgate

# 扫描起点：模拟交易引擎上线（2026-08-18）之前的持仓不存在误执行可能
SCAN_START = date(2026, 8, 18)


async def load_trading_days(end: date) -> set[str]:
    """FQGate 权威交易日历（含节假日安排），失败直接抛错拒绝清理"""
    data = await fq_calendar.trading_days(
        SCAN_START.strftime("%Y%m%d"), (end + timedelta(days=1)).strftime("%Y%m%d")
    )
    days = set(_fqgate._parse_calendar_days(data))
    if not days:
        raise RuntimeError("FQGate 交易日历返回为空，拒绝清理（请确认网关已启动）")
    return days


async def main(apply: bool) -> None:
    today = timezone.now().date()
    trading_days = await load_trading_days(today)
    print(f"交易日历: {min(trading_days)} ~ {max(trading_days)} 共 {len(trading_days)} 个交易日")

    await init_pool()
    try:
        async for db in get_session():
            result = await db.execute(
                select(BusinessStrategyPosition).where(
                    BusinessStrategyPosition.buy_time.is_not(None),
                    BusinessStrategyPosition.deleted_at.is_(None),
                )
            )
            positions = list(result.scalars().all())

            bogus, wrong_sell = [], []
            for pos in positions:
                buy_day = pos.buy_time.date().isoformat()
                sell_day = pos.sell_time.date().isoformat() if pos.sell_time else None
                if buy_day not in trading_days:
                    bogus.append(pos)
                elif sell_day and sell_day not in trading_days:
                    wrong_sell.append(pos)

            print(f"\n== A 类：非交易日买入（误建仓）共 {len(bogus)} 笔 ==")
            for pos in bogus:
                print(
                    f"  position={pos.id} 策略={pos.strategy_name}({pos.strategy_id}) "
                    f"{pos.stock_name}({pos.stock_code}) buy_time={pos.buy_time} "
                    f"price={pos.buy_price} status={pos.status} run_id={pos.run_id}"
                )
            print(f"\n== B 类：非交易日卖出（只报告不处理）共 {len(wrong_sell)} 笔 ==")
            for pos in wrong_sell:
                print(
                    f"  position={pos.id} 策略={pos.strategy_name}({pos.strategy_id}) "
                    f"{pos.stock_name}({pos.stock_code}) buy_time={pos.buy_time} "
                    f"sell_time={pos.sell_time} reason={pos.sell_reason}"
                )

            # C 类：非交易日生成的 pending 信号（陈旧快照产物，下一交易日会被误执行）
            result = await db.execute(
                select(BusinessStrategySignal).where(
                    BusinessStrategySignal.status == "pending",
                    BusinessStrategySignal.deleted_at.is_(None),
                )
            )
            stale_signals = [
                s for s in result.scalars().all()
                if str(s.run_date)[:10] not in trading_days
            ]
            print(f"\n== C 类：非交易日生成的待执行信号共 {len(stale_signals)} 条 ==")
            for sig in stale_signals:
                print(
                    f"  signal={sig.id} 策略 {sig.strategy_id} {sig.stock_name}({sig.stock_code}) "
                    f"action={sig.action} run_date={sig.run_date} run_id={sig.run_id}"
                )

            if not apply:
                print("\n[dry-run] 未做任何修改；确认无误后加 --apply 执行清理")
                return

            now = timezone.now()
            cleaned_positions = 0
            expired_signals = 0
            run_opened_fix: dict[int, int] = {}
            for pos in bogus:
                # 软删持仓（条件 UPDATE 防并发重复处理）
                result = await db.execute(
                    update(BusinessStrategyPosition)
                    .where(
                        BusinessStrategyPosition.id == pos.id,
                        BusinessStrategyPosition.deleted_at.is_(None),
                    )
                    .values(deleted_at=now)
                    .execution_options(synchronize_session=False)
                )
                if (result.rowcount or 0) != 1:
                    continue
                cleaned_positions += 1
                run_opened_fix[pos.run_id] = run_opened_fix.get(pos.run_id, 0) + 1
                # 对应买入信号置 expired
                result = await db.execute(
                    update(BusinessStrategySignal)
                    .where(
                        BusinessStrategySignal.run_id == pos.run_id,
                        BusinessStrategySignal.strategy_id == pos.strategy_id,
                        BusinessStrategySignal.stock_code == pos.stock_code,
                        BusinessStrategySignal.action == "buy",
                        BusinessStrategySignal.status == "executed",
                        BusinessStrategySignal.deleted_at.is_(None),
                    )
                    .values(status="expired", result_msg="非交易日误执行，系统清理")
                    .execution_options(synchronize_session=False)
                )
                expired_signals += result.rowcount or 0
            # 修正来源 run 的建仓计数
            for run_id, count in run_opened_fix.items():
                await db.execute(
                    update(BusinessStrategyRun)
                    .where(BusinessStrategyRun.id == run_id)
                    .values(opened_count=BusinessStrategyRun.opened_count - count)
                    .execution_options(synchronize_session=False)
                )
            # C 类信号置 expired
            expired_stale_signals = 0
            for sig in stale_signals:
                result = await db.execute(
                    update(BusinessStrategySignal)
                    .where(
                        BusinessStrategySignal.id == sig.id,
                        BusinessStrategySignal.status == "pending",
                        BusinessStrategySignal.deleted_at.is_(None),
                    )
                    .values(status="expired", result_msg="非交易日生成的信号，系统清理")
                    .execution_options(synchronize_session=False)
                )
                expired_stale_signals += result.rowcount or 0
            await db.commit()
            print(
                f"\n[apply] 已软删持仓 {cleaned_positions} 笔，"
                f"信号置 expired {expired_signals} 条（误执行买入）"
                f" + {expired_stale_signals} 条（非交易日生成），"
                f"修正 run opened_count {len(run_opened_fix)} 条"
            )
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理非交易日误执行的交易")
    parser.add_argument("--apply", action="store_true", help="实际执行清理（默认 dry-run）")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
