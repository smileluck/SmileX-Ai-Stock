"""
Agent 因子计算工具 —— 供 LLM 通过 Function Calling 计算个股量化因子。

复用 modules/factor 计算服务（行情抓取 + 白名单 DSL 求值），
每个工具用 @register_tool 装饰器声明式注册，自动出现在工具列表中。
工具函数第一个参数固定为 db: AsyncSession（由 tool_registry.execute 注入）。
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.errors import RequestError
from database.models.business.factor import BusinessFactor
from modules.agent.services.tool_registry import register_tool
from modules.factor.services.factor_calc import _fetch_universe_bars
from modules.factor.services.formula import calc_factor_values

logger = logging.getLogger(__name__)

# factor_codes 缺省时计算的核心因子子集
DEFAULT_FACTOR_CODES = [
    "bias5",
    "bias20",
    "roc5",
    "roc20",
    "vr5",
    "rsi14",
    "vol20",
    "alpha101_101",
]

# 单次计算股票数上限（行情抓取按股逐个拉取，过多会显著拖慢）
MAX_CODES = 50

# 回看交易日数（与因子 /calc 端点默认一致，保证窗口函数有足够历史）
LOOKBACK = 120


@register_tool(
    name="calc_stock_factors",
    description=(
        "计算一批个股最新交易日的量化因子值（基于截至最近交易日的日K线，盘中调用同样返回最近收盘口径）。"
        "不传 factor_codes 时默认计算 8 个核心因子："
        "bias5/bias20（乖离率%，收盘价相对5/20日均线偏离，bias20<-5 视为超跌、bias20>8 视为高位）；"
        "roc5/roc20（变动率%，近5/20日涨跌幅，roc20 正负反映中期趋势方向）；"
        "vr5（量比，当日成交量/5日均量，vr5>2 视为明显放量）；"
        "rsi14（相对强弱，0~100 区间，<30 超卖、>70 超买）；"
        "vol20（20日波动率，日涨跌幅标准差，数值越大波动越剧烈）；"
        "alpha101_101（日内强弱，(收-开)/(高-低)，接近 1 表示收在日内高位、接近 -1 表示收在日内低位）。"
        "因子值用于辅助判断买卖点，不构成唯一依据。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "6位股票代码列表，如 [\"600519\", \"000001\"]，单次最多 50 只",
            },
            "factor_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "因子代码列表，留空则计算默认核心子集 "
                    + "/".join(DEFAULT_FACTOR_CODES)
                ),
            },
        },
        "required": ["codes"],
    },
)
async def calc_stock_factors(
    db: AsyncSession,
    codes: list[str],
    factor_codes: Optional[list[str]] = None,
) -> dict[str, Any]:
    """计算股票池最新交易日的因子值。"""
    codes = list(dict.fromkeys(c.strip() for c in codes if c and c.strip()))
    if not codes:
        return {"error": "股票代码列表为空"}
    if len(codes) > MAX_CODES:
        return {"error": f"股票数量超过单次上限 {MAX_CODES} 只（实际 {len(codes)} 只），请分批计算"}
    invalid = [c for c in codes if not re.fullmatch(r"\d{6}", c)]
    if invalid:
        return {"error": f"存在非法股票代码（需为6位数字）: {invalid}"}

    # 解析目标因子：缺省用核心子集；按 code 查启用中的因子
    wanted = list(dict.fromkeys(factor_codes)) if factor_codes else DEFAULT_FACTOR_CODES
    result = await db.execute(
        select(BusinessFactor)
        .where(
            BusinessFactor.code.in_(wanted),
            BusinessFactor.status.is_(True),
            BusinessFactor.deleted_at.is_(None),
        )
        .order_by(BusinessFactor.id)
    )
    factors = list(result.scalars().all())
    if not factors:
        return {"error": f"未找到可用因子: {wanted}"}

    warnings: list[str] = []
    missing = [c for c in wanted if c not in {f.code for f in factors}]
    if missing:
        warnings.append(f"因子代码不存在或已停用，已跳过: {missing}")

    # 抓行情并逐因子计算（复用 factor 模块计算路径）
    try:
        bars_by_code, target_day, fetch_warnings = await _fetch_universe_bars(
            codes, None, LOOKBACK
        )
    except RequestError as e:
        return {"error": getattr(e, "msg", None) or str(e)}
    warnings.extend(fetch_warnings)

    factor_results: dict[str, dict[str, Any]] = {}
    for factor in factors:
        values, calc_warnings = calc_factor_values(factor.formula, bars_by_code)
        warnings.extend(calc_warnings)
        factor_results[factor.code] = {
            "name": factor.name,
            "values": {
                code: (round(values[code], 4) if values.get(code) is not None else None)
                for code in sorted(bars_by_code)
            },
        }

    return {
        "end_date": target_day,
        "factors": factor_results,
        "warnings": warnings,
    }
