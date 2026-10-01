#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 交易日历（/v1/market/calendar/*）。"""
from core.fqgate import client


async def timeline(code: str, market: str) -> dict:
    """市场时间轴：返回指定证券所属市场的交易日、时区和交易时段。不提供证券当前交易状态。"""
    return await client.post(
        "/v1/market/calendar/timeline", {"code": code, "market": market}
    )


async def trading_days(start_date: str, end_date: str) -> dict:
    """交易日：返回指定日期范围内的交易日，无需登录行情账户。日期格式 YYYYMMDD。"""
    return await client.post(
        "/v1/market/calendar/trading-days",
        {"start_date": start_date, "end_date": end_date},
    )
