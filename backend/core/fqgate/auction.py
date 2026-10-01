#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 集合竞价（/v1/market/history/call-auction*）。"""
from core.fqgate import client


async def call_auction(code: str, market: str, date: str | None = None) -> dict:
    """集合竞价数据：返回指定证券的集合竞价数据。date 为可选交易日，格式 YYYYMMDD。"""
    body: dict = {"code": code, "market": market}
    if date is not None:
        body["date"] = date
    return await client.post("/v1/market/history/call-auction", body)


async def call_auction_anomaly(market: str | None = None) -> dict:
    """集合竞价异动：返回指定市场的集合竞价异动；省略市场时查询沪市 A 股。"""
    body: dict = {}
    if market is not None:
        body["market"] = market
    return await client.post("/v1/market/history/call-auction-anomaly", body)
