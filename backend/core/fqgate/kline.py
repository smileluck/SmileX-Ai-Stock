#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate K 线与分时（/v1/market/history/*）。"""
from core.fqgate import client


async def corporate_action(code: str, market: str) -> dict:
    """除权除息数据：返回指定证券的除权除息记录。"""
    return await client.post(
        "/v1/market/history/corporate-action", {"code": code, "market": market}
    )


async def intraday(code: str, market: str) -> dict:
    """当日分时数据：返回指定证券的当日分时数据。"""
    return await client.post(
        "/v1/market/history/intraday", {"code": code, "market": market}
    )


async def klines(
    code: str,
    market: str,
    adjust: str | None = None,
    count: int | None = None,
    end_date: str | None = None,
    interval: str | None = None,
    start_date: str | None = None,
) -> dict:
    """K 线数据：支持按返回数量（count）或日期范围（start_date/end_date 须同时填写）
    查询，两种方式不能同时使用。interval 为周期（如 day），adjust 为复权方式。"""
    body: dict = {"code": code, "market": market}
    if adjust is not None:
        body["adjust"] = adjust
    if count is not None:
        body["count"] = count
    if end_date is not None:
        body["end_date"] = end_date
    if interval is not None:
        body["interval"] = interval
    if start_date is not None:
        body["start_date"] = start_date
    return await client.post("/v1/market/history/klines", body)


async def minute_snapshot(code: str, market: str, date: str | None = None) -> dict:
    """分钟快照：返回指定证券的分钟行情快照，date 为可选交易日（YYYYMMDD）。"""
    body: dict = {"code": code, "market": market}
    if date is not None:
        body["date"] = date
    return await client.post("/v1/market/history/minute-snapshot", body)
