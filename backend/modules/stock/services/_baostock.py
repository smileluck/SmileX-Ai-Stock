#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Baostock 数据源辅助层
作为 akshare（东财）接口的降级源：东财限流/异常时兜底抓取

注意：baostock 是全局单连接协议，login/query/logout 必须在同一线程内串行完成，
不能跨线程并发调用。日线数据盘后更新（当日 bar 一般晚间才可用）。
出站限流/超时统一走 core.datasource.gateway（datasource.* 配置驱动）。
"""
import logging

from core.datasource.gateway import call_external
from modules.stock.services._common import num

logger = logging.getLogger(__name__)

# 查询字段（指数日线）
_INDEX_FIELDS = "date,open,high,low,close,preclose,volume,amount,pctChg"


def to_bs_code(index_code: str) -> str:
    """纯数字指数代码转 baostock 格式：000001 -> sh.000001，399001 -> sz.399001"""
    code = index_code.strip()
    if code.startswith(("0", "5")):
        return f"sh.{code}"
    return f"sz.{code}"


def _fmt_date(d: str) -> str:
    """兼容 YYYYMMDD / YYYY-MM-DD 两种入参，统一输出 YYYY-MM-DD"""
    d = d.strip()
    if len(d) == 8 and "-" not in d:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _bar_to_item(row: dict) -> dict:
    """baostock 行数据转标准化 dict（与 market_fetcher 输出契约一致）"""
    close = num(row.get("close"))
    preclose = num(row.get("preclose"))
    high = num(row.get("high"))
    low = num(row.get("low"))
    return {
        "record_date": row.get("date") or None,
        "open": num(row.get("open")),
        "high": high,
        "low": low,
        "latest_price": close,
        "prev_close": preclose,
        "change_pct": num(row.get("pctChg")),
        "change_amount": round(close - preclose, 4)
        if close is not None and preclose is not None
        else None,
        "volume": num(row.get("volume")),
        "turnover": num(row.get("amount")),
        "amplitude": round((high - low) / preclose * 100, 4)
        if high is not None and low is not None and preclose
        else None,
    }


def _query_index_daily(
    codes: list[str], start_date: str, end_date: str
) -> dict[str, list[dict]]:
    """（同步）登录 baostock 并逐个查询指数日线，返回 {code: [bar, ...]}（按日期升序）"""
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")

    result: dict[str, list[dict]] = {}
    try:
        for code in codes:
            rs = bs.query_history_k_data_plus(
                to_bs_code(code),
                _INDEX_FIELDS,
                start_date=_fmt_date(start_date),
                end_date=_fmt_date(end_date),
                frequency="d",
                adjustflag="3",
            )
            if rs.error_code != "0":
                logger.warning("baostock 查询指数 %s 失败: %s", code, rs.error_msg)
                result[code] = []
                continue
            fields = _INDEX_FIELDS.split(",")
            bars = []
            while rs.next():
                bars.append(_bar_to_item(dict(zip(fields, rs.get_row_data()))))
            result[code] = bars
    finally:
        bs.logout()
    return result


async def fetch_index_daily_bars(
    codes: list[str], start_date: str, end_date: str
) -> dict[str, list[dict]]:
    """异步入口：批量查询指数日线数据（akshare 降级用）

    Args:
        codes: 纯数字指数代码列表，如 ["000001", "399001"]
        start_date / end_date: YYYYMMDD 或 YYYY-MM-DD

    Returns:
        {code: [bar, ...]}，bar 为标准化 dict，按日期升序
    """
    return await call_external("baostock", _query_index_daily, codes, start_date, end_date)


# 成分股查询字段（沪深300 / 中证500 共用）
_CONSTITUENT_FIELDS = "updateDate,code,code_name,weight"

# 支持的成分股指数（baostock 仅提供沪深300与中证500两个成分接口）
_CONSTITUENT_INDEXES = {
    "000300": "沪深300",
    "000905": "中证500",
}


def _query_constituents() -> list[dict]:
    """（同步）登录 baostock 查询沪深300/中证500成分股列表"""
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")

    items: list[dict] = []
    try:
        for index_code, index_name in _CONSTITUENT_INDEXES.items():
            query = (
                bs.query_hs300_stocks() if index_code == "000300"
                else bs.query_zz500_stocks()
            )
            if query.error_code != "0":
                logger.warning(
                    "baostock 查询 %s 成分股失败: %s", index_name, query.error_msg
                )
                continue
            fields = _CONSTITUENT_FIELDS.split(",")
            while query.next():
                row = dict(zip(fields, query.get_row_data()))
                # baostock 代码 sh.600000 -> 600000
                stock_code = str(row.get("code") or "").split(".")[-1]
                if len(stock_code) != 6:
                    continue
                items.append(
                    {
                        "record_date": row.get("updateDate") or None,
                        "index_code": index_code,
                        "index_name": index_name,
                        "stock_code": stock_code,
                        "stock_name": row.get("code_name") or "",
                        "weight": num(row.get("weight")),
                    }
                )
    finally:
        bs.logout()
    return items


async def fetch_index_constituents() -> list[dict]:
    """异步入口：查询沪深300/中证500成分股列表（蓝筹白马策略数据源）

    Returns:
        [{record_date, index_code, index_name, stock_code, stock_name, weight}, ...]
    """
    return await call_external("baostock", _query_constituents)
