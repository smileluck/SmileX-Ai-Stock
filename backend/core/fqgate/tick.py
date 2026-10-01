#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 盘口与逐笔（/v1/market/history/*、/v1/market/order-book/*）。"""
from core.fqgate import client


async def depth(securities: list[dict]) -> dict:
    """五档盘口：返回买卖五档价格及数量，不包含每档的逐笔委托队列。"""
    return await client.post("/v1/market/history/depth", {"securities": securities})


async def super_tick(code: str, market: str, date: str | None = None) -> dict:
    """扩展成交明细：返回指定证券的增强逐笔行情，可选交易日（YYYYMMDD）。

    records 按数据段保留：除逐笔行情外，还可能包含按日提供的补充数据。
    逐笔段的字段 1 为 Unix 秒时间戳；日级补充段的字段 1 为 YYYYMMDD 日期，
    可能早于所选交易日。请勿将补充段计入逐笔条数；row_count 为所有段的总行数。
    """
    body = {"code": code, "market": market}
    if date is not None:
        body["date"] = date
    return await client.post("/v1/market/history/super-tick", body)


async def tick(code: str, market: str) -> dict:
    """普通成交明细：保留行情服务的记录粒度；不提供 Level-2 原始逐笔成交。"""
    return await client.post(
        "/v1/market/history/tick", {"code": code, "market": market}
    )


async def ask(
    code: str,
    market: str | None = None,
    start_level: int | None = None,
    end_level: int | None = None,
) -> dict:
    """卖方委托队列：返回查询时点的卖方盘口，最多二十档；每档包含逐项委托数量。

    start_level 省略时从第一档开始；end_level 最多第二十档；
    code 已包含四字符市场前缀时 market 可省略。
    """
    body = {"code": code}
    if market is not None:
        body["market"] = market
    if start_level is not None:
        body["start_level"] = start_level
    if end_level is not None:
        body["end_level"] = end_level
    return await client.post("/v1/market/order-book/ask", body)


async def bid(
    code: str,
    market: str | None = None,
    start_level: int | None = None,
    end_level: int | None = None,
) -> dict:
    """买方委托队列：返回查询时点的买方盘口，最多二十档；每档包含逐项委托数量。

    start_level 省略时从第一档开始；end_level 最多第二十档；
    code 已包含四字符市场前缀时 market 可省略。
    """
    body = {"code": code}
    if market is not None:
        body["market"] = market
    if start_level is not None:
        body["start_level"] = start_level
    if end_level is not None:
        body["end_level"] = end_level
    return await client.post("/v1/market/order-book/bid", body)
