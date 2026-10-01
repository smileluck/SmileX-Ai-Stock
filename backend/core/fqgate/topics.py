#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 市场专题（/v1/market/topics/*）。"""
from core.fqgate import client


async def limit_up_statistics(
    date: str | None = None, filters: list | None = None
) -> dict:
    """涨跌停统计：返回当日与前一交易日的涨停、跌停、开板、触板数量及封板率，
    可按市场范围筛选，无需登录行情账户。date 格式 YYYYMMDD，省略时返回最近交易日；
    filters 为统计范围，省略时不限定板块。"""
    body: dict = {}
    if date is not None:
        body["date"] = date
    if filters is not None:
        body["filters"] = filters
    return await client.post("/v1/market/topics/limit-up-statistics", body)
