#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略回测引擎（纯函数，不依赖数据库/网络，可独立 smoke 测试）

信号源 = 回放已记录的真实 AI 信号（business_strategy_signal），
不做 LLM 逐日重放：行情/资讯快照是当前值，逐日重放存在前视偏差。

撮合语义（与实盘交易引擎 trade_engine / position_service 对齐）：
- 信号统一在「产生日之后的第一个交易日」按开盘价成交（盘后/盘中信号口径统一，
  即 run_date < D 的未执行信号在交易日 D 的开盘价执行）
- 每日执行顺序：先卖后买再 adjust（复用实盘 _ACTION_ORDER 语义）
- T+1：当日买入的持仓当日不可卖出（信号卖出顺延，止损/止盈/回撤同样受限）
- 止损/目标价 sanity 修正：等价于 trade_engine._sanitize_price_levels
  （该函数为 strategy 模块私有，这里实现等价逻辑）
- 离场检查：止损（跳空按 open）> 目标价（涨停暂缓顺延）> 回撤止盈，同日同时触及
  止损与目标时保守按止损处理
- 费用：佣金（双边，最低 5 元）+ 印花税（仅卖出）；滑点仅应用于信号驱动的
  买/卖成交价，止损/止盈/回撤/期末强平按规则价成交不再叠加滑点
- 区间结束仍持仓的按最后一个交易日收盘价强制平仓（backtest_end）
"""
import logging
import math
from typing import Any, Optional

from modules.strategy.services.position_service import limit_up_threshold

logger = logging.getLogger(__name__)

# 信号执行顺序：先卖（腾出仓位与资金）后买再调整
_ACTION_ORDER = {"sell": 0, "buy": 1, "adjust": 2}

# 佣金最低收费（元）
_MIN_COMMISSION = 5.0

# 年化交易日数
_TRADING_DAYS_PER_YEAR = 252


def _sanitize_price_levels(
    price: float,
    stop_loss_price: Optional[float],
    target_sell_price: Optional[float],
    stop_loss_pct: Optional[float],
    take_profit_pct: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """价格位 sanity 修正（等价 trade_engine._sanitize_price_levels）：
    AI 给的止损价可能高于买价、目标价可能低于买价，会导致建仓即触发平仓；
    无效价格位按策略止损/止盈百分比重算。"""
    stop = stop_loss_price
    if stop is None or stop >= price:
        stop = round(price * (1 - stop_loss_pct / 100), 4) if stop_loss_pct is not None else None
    target = target_sell_price
    if target is None or target <= price:
        target = round(price * (1 + take_profit_pct / 100), 4) if take_profit_pct is not None else None
    return stop, target


def _commission(amount: float, commission_pct: float) -> float:
    """佣金：按成交额比例，最低 5 元"""
    if amount <= 0:
        return 0.0
    return max(amount * commission_pct / 100, _MIN_COMMISSION)


def run_replay(
    *,
    signals: list[dict[str, Any]],
    bars_by_code: dict[str, dict[str, dict]],
    trading_days: list[str],
    initial_capital: float,
    max_positions: int,
    slippage_pct: float,
    commission_pct: float,
    stamp_tax_pct: float,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None,
    trailing_drawdown_pct: Optional[float] = None,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    """逐日回放撮合。

    Args:
        signals: 已按 run_date+id 升序的信号列表，每项含
            stock_code/stock_name/action(buy/sell/adjust)/run_date/
            target_sell_price/stop_loss_price/reason；adjust 与未知动作在此被忽略
        bars_by_code: {stock_code: {date: bar}}，bar 含 open/high/low/close/pct_chg
        trading_days: 交易日序列（YYYY-MM-DD 升序），来自上证指数日线
        warnings: 外部已收集的告警（北交所跳过等），本函数会追加

    Returns:
        {"result": 绩效汇总 dict, "equity_curve": [...], "trades": [成交明细 dict, ...]}
    """
    warnings = warnings if warnings is not None else []
    cash = float(initial_capital)
    position_budget = float(initial_capital) / max(max_positions, 1)

    # stock_code -> 持仓 dict
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []

    pending = [s for s in signals if s.get("action") in _ACTION_ORDER]

    def _record_trade(**kw) -> None:
        trades.append(kw)

    def _close_position(code: str, pos: dict, date: str, price: float, reason: str) -> None:
        nonlocal cash
        price = round(price, 4)
        amount = round(pos["quantity"] * price, 2)
        fee = round(
            _commission(amount, commission_pct) + amount * stamp_tax_pct / 100, 2
        )
        cash += amount - fee
        buy_price = pos["buy_price"]
        return_rate = round((price - buy_price) / buy_price * 100, 4) if buy_price else None
        pnl = (price - buy_price) * pos["quantity"] - pos["buy_fee"] - fee
        _record_trade(
            stock_code=code, stock_name=pos["stock_name"], action="sell",
            trade_date=date, price=price, quantity=pos["quantity"],
            amount=amount, fee=fee, reason=reason, return_rate=return_rate,
            _pnl=round(pnl, 2),
        )
        del positions[code]

    for day in trading_days:
        # ---- 1. 执行信号：run_date < day 的未执行信号按当日开盘价成交（先卖后买再调整） ----
        due = [s for s in pending if s["run_date"] < day]
        due.sort(key=lambda s: _ACTION_ORDER.get(s["action"], 9))
        for sig in due:
            code = sig["stock_code"]
            bar = bars_by_code.get(code, {}).get(day)
            if bar is None or not bar.get("open"):
                continue  # 当日停牌/缺行情，顺延至下一交易日
            open_price = bar["open"]
            pos = positions.get(code)

            if sig["action"] == "sell":
                if pos is None:
                    pending.remove(sig)  # 无持仓可卖，跳过
                    continue
                if pos["buy_date"] == day:
                    continue  # T+1：当日买入不可卖，顺延
                sell_price = round(open_price * (1 - slippage_pct / 100), 4)
                _close_position(code, pos, day, sell_price, "ai_signal")
                pending.remove(sig)
                continue

            if sig["action"] == "buy":
                if pos is not None:
                    pending.remove(sig)  # 已持仓同票，跳过
                    continue
                if len(positions) >= max_positions:
                    pending.remove(sig)  # 达最大持仓数，跳过
                    continue
                buy_price = round(open_price * (1 + slippage_pct / 100), 4)
                quantity = int(position_budget / buy_price / 100) * 100
                if quantity <= 0:
                    pending.remove(sig)
                    warnings.append(
                        f"{day} {code} 买入跳过：等权预算 {position_budget:.2f} 不足买入一手（价 {buy_price}）"
                    )
                    continue
                amount = round(quantity * buy_price, 2)
                fee = round(_commission(amount, commission_pct), 2)
                if amount + fee > cash:
                    pending.remove(sig)
                    warnings.append(
                        f"{day} {code} 买入跳过：资金不足（需 {amount + fee:.2f}，可用 {cash:.2f}）"
                    )
                    continue
                stop, target = _sanitize_price_levels(
                    buy_price, sig.get("stop_loss_price"), sig.get("target_sell_price"),
                    stop_loss_pct, take_profit_pct,
                )
                cash -= amount + fee
                positions[code] = {
                    "stock_name": sig.get("stock_name") or code,
                    "buy_date": day,
                    "buy_price": buy_price,
                    "buy_fee": fee,
                    "quantity": quantity,
                    "target": target,
                    "stop": stop,
                    "trailing_pct": trailing_drawdown_pct,
                    "peak": buy_price,
                    "last_close": bar.get("close") or buy_price,
                }
                _record_trade(
                    stock_code=code, stock_name=sig.get("stock_name") or code,
                    action="buy", trade_date=day, price=buy_price, quantity=quantity,
                    amount=amount, fee=fee, reason=sig.get("reason"), return_rate=None,
                    _pnl=None,
                )
                pending.remove(sig)
                continue

            # adjust：更新持仓的卖点/止损（方向校验同实盘，参考价为当日开盘价）
            if pos is None:
                pending.remove(sig)  # 无持仓可调整，跳过
                continue
            if sig.get("target_sell_price") and sig["target_sell_price"] > open_price:
                pos["target"] = sig["target_sell_price"]
            if sig.get("stop_loss_price") and sig["stop_loss_price"] < open_price:
                pos["stop"] = sig["stop_loss_price"]
            pending.remove(sig)

        # ---- 2. 持仓离场检查（当日 bar 的 high/low/close，T+1 同实盘约束） ----
        for code, pos in list(positions.items()):
            bar = bars_by_code.get(code, {}).get(day)
            if bar is None or not bar.get("close"):
                continue  # 停牌/缺行情：不刷新峰值、不做离场判断，净值沿用 last_close
            pos["last_close"] = bar["close"]
            # 回撤止盈基准：持仓期间各日 high 滚动刷新（买入当日也计入）
            if bar.get("high"):
                pos["peak"] = max(pos["peak"], bar["high"])
            if pos["buy_date"] == day:
                continue  # T+1：当日买入不可卖

            # 止损优先（同日同时触及止损与目标时，保守按止损处理）
            if pos["stop"] and bar.get("low") is not None and bar["low"] <= pos["stop"]:
                fill = bar["open"] if bar["open"] < pos["stop"] else pos["stop"]
                _close_position(code, pos, day, fill, "stop_loss")
                continue
            # 止盈/目标价
            if pos["target"] and bar.get("high") is not None and bar["high"] >= pos["target"]:
                # 涨停暂缓（实盘语义）：当日封涨停不平仓，顺延下一交易日再判定
                pct_chg = bar.get("pct_chg")
                if pct_chg is not None and pct_chg >= limit_up_threshold(code):
                    continue
                fill = bar["open"] if bar["open"] > pos["target"] else pos["target"]
                _close_position(code, pos, day, fill, "target_reached")
                continue
            # 回撤止盈：自峰值回撤超阈值且仍浮盈（跌破买价交由止损线处理）
            trailing_pct = pos.get("trailing_pct")
            if trailing_pct and pos["peak"] > 0:
                drawdown_pct = (pos["peak"] - bar["close"]) / pos["peak"] * 100
                if drawdown_pct >= trailing_pct and bar["close"] > pos["buy_price"]:
                    _close_position(code, pos, day, bar["close"], "trailing_stop")

        # ---- 3. 收盘记账 ----
        market_value = round(
            sum(p["quantity"] * p["last_close"] for p in positions.values()), 2
        )
        equity = round(cash + market_value, 2)
        equity_curve.append({
            "date": day,
            "equity": equity,
            "cash": round(cash, 2),
            "market_value": market_value,
        })

    # ---- 4. 期末强平：区间结束仍持仓的按最后一个交易日收盘价平仓 ----
    if trading_days:
        last_day = trading_days[-1]
        for code, pos in list(positions.items()):
            _close_position(code, pos, last_day, pos["last_close"], "backtest_end")
        if equity_curve:
            equity_curve[-1]["equity"] = round(cash, 2)
            equity_curve[-1]["cash"] = round(cash, 2)
            equity_curve[-1]["market_value"] = 0.0

    # 到期仍未执行的信号（产生日之后无交易日 / 始终停牌缺行情）
    if pending:
        warnings.append(f"{len(pending)} 条信号在回测区间内未执行（产生日后无交易日或标的缺行情）")

    return {
        "result": _build_metrics(trades, equity_curve, float(initial_capital), warnings),
        "equity_curve": equity_curve,
        "trades": [
            {k: v for k, v in t.items() if not k.startswith("_")} for t in trades
        ],
    }


def _build_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    initial_capital: float,
    warnings: list[str],
) -> dict[str, Any]:
    """由成交明细与净值曲线计算绩效汇总"""
    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
    total_return_pct = round((final_equity / initial_capital - 1) * 100, 4) if initial_capital else None

    n_days = len(equity_curve)
    annual_return_pct = None
    if n_days >= 1 and initial_capital and final_equity > 0:
        annual_return_pct = round(
            ((final_equity / initial_capital) ** (_TRADING_DAYS_PER_YEAR / n_days) - 1) * 100, 4
        )

    # 最大回撤（按净值曲线）
    max_drawdown_pct = None
    if equity_curve:
        peak_eq = equity_curve[0]["equity"]
        max_dd = 0.0
        for point in equity_curve:
            eq = point["equity"]
            if eq > peak_eq:
                peak_eq = eq
            if peak_eq > 0:
                max_dd = max(max_dd, (peak_eq - eq) / peak_eq * 100)
        max_drawdown_pct = round(max_dd, 4)

    # 夏普比率：日收益率序列，rf=0，年化 ×√252；样本不足 2 天为零波动时 None
    sharpe = None
    if n_days >= 2:
        daily_returns = [
            equity_curve[i]["equity"] / equity_curve[i - 1]["equity"] - 1
            for i in range(1, n_days)
            if equity_curve[i - 1]["equity"] > 0
        ]
        if len(daily_returns) >= 2:
            mean_r = sum(daily_returns) / len(daily_returns)
            var = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            std_r = math.sqrt(var)
            if std_r > 0:
                sharpe = round(mean_r / std_r * math.sqrt(_TRADING_DAYS_PER_YEAR), 4)

    sells = [t for t in trades if t["action"] == "sell"]
    win_count = sum(1 for t in sells if (t.get("return_rate") or 0) > 0)
    loss_count = len(sells) - win_count
    win_rate = round(win_count / len(sells) * 100, 4) if sells else None

    gross_profit = sum(t["_pnl"] for t in sells if t.get("_pnl") and t["_pnl"] > 0)
    gross_loss = sum(-t["_pnl"] for t in sells if t.get("_pnl") and t["_pnl"] < 0)
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else None

    return {
        "total_return_pct": total_return_pct,
        "annual_return_pct": annual_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe": sharpe,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "trade_count": sum(1 for t in trades if t["action"] == "buy"),
        "final_equity": final_equity,
        "warnings": warnings,
    }
