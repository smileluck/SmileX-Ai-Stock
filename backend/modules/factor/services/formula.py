#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
因子公式 DSL 安全求值器（严禁 eval/exec，基于 ast 白名单解析）

语法：
- 字段变量（每股日线序列，值缺失为 NaN）：
  open high low close volume amount preclose pct_chg，派生 vwap = amount/volume
- 时间序列函数（窗口 n 为正整数常量）：
  REF(x,n) MA(x,n) SUM(x,n) MAX(x,n) MIN(x,n) STD(x,n) DELTA(x,n)
  CORR(x,y,n)（滚动相关） COUNT(cond,n)（窗口内条件为真的天数）
- 逐元素标量函数：ABS LOG（非正数取 NaN） SQRT（负数取 NaN） SIGN IF(cond,a,b)
- 截面函数：RANK(x) —— 对计算日的截面值在选股 universe 内归一化排名 (0,1]
  （值越大越接近 1），仅允许顶层或嵌套在算术/比较运算中，
  不允许作为时间序列函数参数（滚动窗口内的截面排名不在本 DSL 范围内）
- 运算符：+ - * / 与比较 > >= < <= ==，括号，一元正负号；序列与标量混合运算（广播）

两段式求值：
1. 每股阶段：全部时间序列计算在单票序列上完成，RANK 节点记为延迟节点
   （内层表达式先算成序列，按出现顺序对齐各股的 rank_inners）
2. 截面阶段：对每个 RANK 节点取各股内层序列的目标日值做截面归一化排名，
   替换回各股表达式树后求目标日因子值
"""
import ast
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from core.exception.errors import CustomError
from core.response.response_code import CustomErrorCode

logger = logging.getLogger(__name__)

# 字段变量（小写）
_FIELD_NAMES = {
    "open", "high", "low", "close", "volume", "amount", "preclose", "pct_chg", "vwap",
}

# 时间序列函数（大写）-> 参数个数
_TS_FUNCS = {
    "REF": 2, "MA": 2, "SUM": 2, "MAX": 2, "MIN": 2, "STD": 2, "DELTA": 2,
    "CORR": 3, "COUNT": 2,
}

# 逐元素标量函数
_SCALAR_FUNCS = {"ABS": 1, "LOG": 1, "SQRT": 1, "SIGN": 1, "IF": 3}

# 截面函数
_RANK_FUNC = "RANK"

_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_CMP_OPS = (ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq)
_UNARY_OPS = (ast.USub, ast.UAdd)


def _invalid(msg: str) -> CustomError:
    return CustomError(error=CustomErrorCode.FACTOR_FORMULA_INVALID, msg=f"因子公式非法：{msg}")


# ----------------------------------------------------------------------
# 结构校验（保存因子时调用，不实际计算）
# ----------------------------------------------------------------------
def validate_formula(formula: str) -> ast.Expression:
    """解析并白名单校验公式，返回 AST；非法公式抛 FACTOR_FORMULA_INVALID（中文说明）"""
    text = (formula or "").strip()
    if not text:
        raise _invalid("公式不能为空")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise _invalid(f"语法错误（{exc.msg}）") from exc
    _check_node(tree.body, allow_rank=True, top_level=True)
    return tree


def _check_node(node: ast.AST, *, allow_rank: bool, top_level: bool) -> None:
    """递归白名单校验。allow_rank 仅在顶层或算术/比较运算内部为 True
    （进入时间序列函数参数后禁止 RANK）。"""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise _invalid("常量仅支持数值")
        return
    if isinstance(node, ast.Name):
        if node.id not in _FIELD_NAMES:
            raise _invalid(
                f"未知变量 [{node.id}]，可用字段: {sorted(_FIELD_NAMES)}"
            )
        return
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _BIN_OPS):
            raise _invalid("仅支持 + - * / 运算符")
        _check_node(node.left, allow_rank=allow_rank, top_level=False)
        _check_node(node.right, allow_rank=allow_rank, top_level=False)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _UNARY_OPS):
            raise _invalid("仅支持一元正负号")
        _check_node(node.operand, allow_rank=allow_rank, top_level=False)
        return
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise _invalid("不支持链式比较（如 a < b < c），请拆分为单条比较")
        if not isinstance(node.ops[0], _CMP_OPS):
            raise _invalid("仅支持 > >= < <= == 比较符")
        _check_node(node.left, allow_rank=allow_rank, top_level=False)
        _check_node(node.comparators[0], allow_rank=allow_rank, top_level=False)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise _invalid("仅支持白名单函数调用，禁止属性/间接调用")
        name = node.func.id
        if node.keywords:
            raise _invalid("不支持关键字参数")
        if name == _RANK_FUNC:
            if not allow_rank:
                raise _invalid("RANK 仅允许顶层或嵌套在算术/比较运算中，不能作为时间序列函数参数")
            if len(node.args) != 1:
                raise _invalid("RANK 接受 1 个参数")
            _check_node(node.args[0], allow_rank=False, top_level=False)
            return
        argc = _TS_FUNCS.get(name) or _SCALAR_FUNCS.get(name)
        if argc is None:
            raise _invalid(
                f"未知函数 [{name}]，时间序列函数: {sorted(_TS_FUNCS)}，"
                f"标量函数: {sorted(_SCALAR_FUNCS)}，截面函数: [RANK]"
            )
        if len(node.args) != argc:
            raise _invalid(f"函数 {name} 需要 {argc} 个参数，实际 {len(node.args)} 个")
        for i, arg in enumerate(node.args):
            # 窗口参数必须是正整数常量（时间序列函数的最后一个参数）
            if name in _TS_FUNCS and i == argc - 1:
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, int)
                        and not isinstance(arg.value, bool) and arg.value > 0):
                    raise _invalid(f"函数 {name} 的窗口参数必须为正整数常量")
                continue
            _check_node(arg, allow_rank=False, top_level=False)
        return
    raise _invalid(f"不支持的语法节点 [{type(node).__name__}]（禁止属性访问/下标/布尔运算等）")


# ----------------------------------------------------------------------
# 求值
# ----------------------------------------------------------------------
# 具体值：float | np.ndarray；延迟值：含 RANK 的表达式树
@dataclass
class _Node:
    """含 RANK 的延迟表达式节点（op 为 add/sub/mul/div/neg/pos/gt/gte/lt/lte/eq/if/rank）"""
    op: str
    args: list[Any]


@dataclass
class _EvalContext:
    """每股求值上下文：RANK 内层序列按出现顺序登记，跨股按序对齐"""
    rank_inners: list[Any] = field(default_factory=list)


def _is_deferred(v: Any) -> bool:
    return isinstance(v, _Node)


def _to_array(v: Any, length: int) -> np.ndarray:
    """标量广播为序列"""
    if isinstance(v, np.ndarray):
        return v
    return np.full(length, float(v))


def _sanitize(arr: np.ndarray) -> np.ndarray:
    """±inf 统一转 NaN"""
    return np.where(np.isfinite(arr), arr, np.nan)


def _require_concrete(v: Any, func_name: str) -> Any:
    if _is_deferred(v):
        raise _invalid(f"RANK 不能作为时间序列/标量函数 {func_name} 的参数")
    return v


_BIN_OP_MAP = {
    ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div",
}
_CMP_OP_MAP = {
    ast.Gt: "gt", ast.GtE: "gte", ast.Lt: "lt", ast.LtE: "lte", ast.Eq: "eq",
}


def _apply_binop(op: str, left: Any, right: Any, length: int) -> Any:
    if _is_deferred(left) or _is_deferred(right):
        return _Node(op, [left, right])
    with np.errstate(divide="ignore", invalid="ignore"):
        l_arr = _to_array(left, length)
        r_arr = _to_array(right, length)
        if op == "add":
            return _sanitize(l_arr + r_arr)
        if op == "sub":
            return _sanitize(l_arr - r_arr)
        if op == "mul":
            return _sanitize(l_arr * r_arr)
        if op == "div":
            return _sanitize(l_arr / r_arr)
    raise _invalid(f"未知运算符 {op}")


def _apply_cmp(op: str, left: Any, right: Any, length: int) -> Any:
    if _is_deferred(left) or _is_deferred(right):
        return _Node(op, [left, right])
    l_arr = _to_array(left, length)
    r_arr = _to_array(right, length)
    if op == "gt":
        return l_arr > r_arr
    if op == "gte":
        return l_arr >= r_arr
    if op == "lt":
        return l_arr < r_arr
    if op == "lte":
        return l_arr <= r_arr
    return l_arr == r_arr


def _apply_ts_func(name: str, args: list[Any], length: int) -> np.ndarray:
    """时间序列函数求值（参数已确保为具体值）"""
    if name == "CORR":
        x = _to_array(_require_concrete(args[0], name), length)
        y = _to_array(_require_concrete(args[1], name), length)
        n = int(args[2])
        return pd.Series(x).rolling(n).corr(pd.Series(y)).to_numpy()

    x = _to_array(_require_concrete(args[0], name), length)
    n = int(args[1])
    s = pd.Series(x)
    if name == "REF":
        return s.shift(n).to_numpy()
    if name == "MA":
        return s.rolling(n).mean().to_numpy()
    if name == "SUM":
        return s.rolling(n).sum().to_numpy()
    if name == "MAX":
        return s.rolling(n).max().to_numpy()
    if name == "MIN":
        return s.rolling(n).min().to_numpy()
    if name == "STD":
        return s.rolling(n).std().to_numpy()
    if name == "DELTA":
        return (s - s.shift(n)).to_numpy()
    if name == "COUNT":
        cond = np.asarray(args[0], dtype=bool)
        return pd.Series(cond.astype(float)).rolling(n).sum().to_numpy()
    raise _invalid(f"未知时间序列函数 {name}")


def _apply_scalar_func(name: str, args: list[Any], length: int) -> Any:
    if name == "IF":
        cond = _require_concrete(args[0], name)
        a = _require_concrete(args[1], name)
        b = _require_concrete(args[2], name)
        cond_arr = np.asarray(_to_array(np.asarray(cond, dtype=float), length), dtype=bool)
        return _sanitize(np.where(cond_arr, _to_array(a, length), _to_array(b, length)))

    x = _to_array(_require_concrete(args[0], name), length)
    with np.errstate(divide="ignore", invalid="ignore"):
        if name == "ABS":
            return np.abs(x)
        if name == "LOG":
            return np.where(x > 0, np.log(np.where(x > 0, x, 1.0)), np.nan)
        if name == "SQRT":
            return np.where(x >= 0, np.sqrt(np.where(x >= 0, x, 0.0)), np.nan)
        if name == "SIGN":
            return np.sign(x)
    raise _invalid(f"未知标量函数 {name}")


def _eval(node: ast.AST, env: dict[str, np.ndarray], ctx: _EvalContext, length: int) -> Any:
    """递归求值：返回 float | np.ndarray | _Node（含 RANK 的延迟表达式）"""
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, env, ctx, length)
        right = _eval(node.right, env, ctx, length)
        return _apply_binop(_BIN_OP_MAP[type(node.op)], left, right, length)
    if isinstance(node, ast.UnaryOp):
        val = _eval(node.operand, env, ctx, length)
        if isinstance(node.op, ast.UAdd):
            return val
        if _is_deferred(val):
            return _Node("neg", [val])
        return -_to_array(val, length)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env, ctx, length)
        right = _eval(node.comparators[0], env, ctx, length)
        return _apply_cmp(_CMP_OP_MAP[type(node.ops[0])], left, right, length)
    if isinstance(node, ast.Call):
        name = node.func.id
        if name == _RANK_FUNC:
            inner = _eval(node.args[0], env, ctx, length)
            if _is_deferred(inner):
                raise _invalid("不支持嵌套 RANK")
            ctx.rank_inners.append(inner)
            return _Node("rank", [len(ctx.rank_inners) - 1])
        args = [_eval(a, env, ctx, length) for a in node.args]
        if name in _TS_FUNCS:
            return _apply_ts_func(name, args, length)
        return _apply_scalar_func(name, args, length)
    raise _invalid(f"不支持的语法节点 [{type(node).__name__}]")


def _resolve(node: Any, rank_scalars: dict[int, float], length: int) -> Any:
    """截面阶段：把延迟表达式树中的 RANK 节点替换为本股截面标量后求值"""
    if not _is_deferred(node):
        return node
    op = node.op
    if op == "rank":
        return rank_scalars.get(node.args[0], np.nan)
    args = [_resolve(a, rank_scalars, length) for a in node.args]
    if op == "neg":
        return -_to_array(args[0], length)
    if op in ("add", "sub", "mul", "div"):
        return _apply_binop(op, args[0], args[1], length)
    if op in ("gt", "gte", "lt", "lte", "eq"):
        return _apply_cmp(op, args[0], args[1], length)
    if op == "if":
        cond_arr = np.asarray(_to_array(args[0], length), dtype=bool)
        return _sanitize(np.where(cond_arr, _to_array(args[1], length), _to_array(args[2], length)))
    raise _invalid(f"未知延迟节点 {op}")


def _last_value(v: Any, length: int) -> float:
    """取目标日（序列末位）值；标量原样返回"""
    if isinstance(v, np.ndarray):
        return float(v[-1]) if length else np.nan
    if isinstance(v, (bool, np.bool_)):
        return float(v)
    return float(v)


# ----------------------------------------------------------------------
# 对外入口
# ----------------------------------------------------------------------
def bars_to_env(bars: list[dict]) -> dict[str, np.ndarray]:
    """bar dict 列表（日期升序）转字段序列环境，缺失值补 NaN"""
    length = len(bars)

    def col(key: str) -> np.ndarray:
        return np.array(
            [float(b[key]) if b.get(key) is not None else np.nan for b in bars],
            dtype=float,
        )

    env = {
        "open": col("open"), "high": col("high"), "low": col("low"),
        "close": col("close"), "volume": col("volume"), "amount": col("amount"),
        "preclose": col("preclose"), "pct_chg": col("pct_chg"),
    }
    with np.errstate(divide="ignore", invalid="ignore"):
        env["vwap"] = _sanitize(env["amount"] / env["volume"])
    return env


def calc_factor_values(
    formula: str, bars_by_code: dict[str, list[dict]]
) -> tuple[dict[str, float], list[str]]:
    """对 universe 内各股计算目标日（bars 末位）因子值。

    Returns:
        (values, warnings)：values 为 {code: 因子值}；
        历史序列不足/公式结果为 NaN 的股票跳过并记入 warnings
    """
    tree = validate_formula(formula)
    warnings: list[str] = []

    # ---- 每股阶段：时间序列求值，登记 RANK 内层序列 ----
    per_stock: dict[str, tuple[Any, list[Any], int]] = {}
    for code, bars in bars_by_code.items():
        if not bars:
            warnings.append(f"股票 {code} 无行情数据，跳过")
            continue
        env = bars_to_env(bars)
        ctx = _EvalContext()
        value = _eval(tree.body, env, ctx, len(bars))
        per_stock[code] = (value, ctx.rank_inners, len(bars))

    if not per_stock:
        return {}, warnings

    # ---- 截面阶段：各 RANK 节点按内层序列目标日值在 universe 内归一化排名 (0,1] ----
    rank_count = max((len(inners) for _, inners, _ in per_stock.values()), default=0)
    # rank_scalars_all[code][rank_idx] = 截面排名标量（NaN 表示该股不参与排名）
    rank_scalars_all: dict[str, dict[int, float]] = {code: {} for code in per_stock}
    for rank_idx in range(rank_count):
        targets: dict[str, float] = {}
        for code, (_, inners, length) in per_stock.items():
            if rank_idx < len(inners):
                targets[code] = _last_value(inners[rank_idx], length)
        finite = {c: v for c, v in targets.items() if np.isfinite(v)}
        ordered = sorted(finite, key=lambda c: finite[c])
        total = len(ordered)
        for pos, code in enumerate(ordered, start=1):
            rank_scalars_all[code][rank_idx] = pos / total if total else np.nan

    # ---- 求各股目标日因子值 ----
    values: dict[str, float] = {}
    for code, (value, _, length) in per_stock.items():
        resolved = _resolve(value, rank_scalars_all[code], length)
        result = _last_value(resolved, length)
        if np.isfinite(result):
            values[code] = round(result, 6)
        else:
            warnings.append(f"股票 {code} 因子值为 NaN（历史序列不足或公式结果无效），跳过")
    return values, warnings


def calc_factor_series(
    formula: str, bars_by_code: dict[str, list[dict]]
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """对 universe 内各股计算全历史因子序列（供回测逐日评估，避免逐日重算）。

    与 calc_factor_values 的差异：
    - 返回每个交易日的因子值而非仅末位值
    - RANK 截面按交易日逐日归一化（每日只对当日有值的股票排名），无前视：
      D 日的因子值只由 ≤D 的 bars 算出

    Returns:
        (series, warnings)：series 为 {code: {date: 因子值}}（仅含有限值的日期）
    """
    tree = validate_formula(formula)
    warnings: list[str] = []

    # ---- 每股阶段：时间序列求值，登记 RANK 内层序列 ----
    per_stock: dict[str, tuple[Any, list[Any], list[str], int]] = {}
    for code, bars in bars_by_code.items():
        if not bars:
            warnings.append(f"股票 {code} 无行情数据，跳过")
            continue
        env = bars_to_env(bars)
        ctx = _EvalContext()
        value = _eval(tree.body, env, ctx, len(bars))
        per_stock[code] = (value, ctx.rank_inners, [b["date"] for b in bars], len(bars))

    if not per_stock:
        return {}, warnings

    # ---- 截面阶段：各 RANK 节点按交易日逐日跨 universe 归一化排名 (0,1] ----
    rank_count = max((len(inners) for _, inners, _, _ in per_stock.values()), default=0)
    idx_by_date = {
        code: {d: i for i, d in enumerate(dates)}
        for code, (_, _, dates, _) in per_stock.items()
    }
    # rank_series_all[code][rank_idx] = 与该股日期序列对齐的截面排名数组
    rank_series_all: dict[str, dict[int, Any]] = {code: {} for code in per_stock}
    for rank_idx in range(rank_count):
        inners_arr: dict[str, np.ndarray] = {}
        all_dates: set[str] = set()
        for code, (_, inners, dates, length) in per_stock.items():
            if rank_idx < len(inners):
                inners_arr[code] = _to_array(inners[rank_idx], length)
                all_dates.update(dates)
        for code, arr in inners_arr.items():
            rank_series_all[code][rank_idx] = np.full(len(arr), np.nan)
        for date in all_dates:
            entries: list[tuple[str, int, float]] = []
            for code, arr in inners_arr.items():
                i = idx_by_date[code].get(date)
                if i is not None and np.isfinite(arr[i]):
                    entries.append((code, i, float(arr[i])))
            entries.sort(key=lambda e: e[2])
            total = len(entries)
            for pos, (code, i, _) in enumerate(entries, start=1):
                rank_series_all[code][rank_idx][i] = pos / total if total else np.nan

    # ---- 求各股全序列因子值 ----
    series: dict[str, dict[str, float]] = {}
    for code, (value, _, dates, length) in per_stock.items():
        resolved = _resolve(value, rank_series_all[code], length)
        arr = _to_array(resolved, length)
        day_values = {
            dates[i]: round(float(arr[i]), 6)
            for i in range(length)
            if np.isfinite(arr[i])
        }
        if day_values:
            series[code] = day_values
        else:
            warnings.append(f"股票 {code} 因子序列全为 NaN（历史序列不足或公式结果无效），跳过")
    return series, warnings
