#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 行情（/v1/market/realtime/*）。"""
from core.fqgate import client


async def block(securities: list[dict], query_key: str | None = None) -> dict:
    """板块行情：按常用字段返回板块实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/block", body)


async def bond(securities: list[dict], query_key: str | None = None) -> dict:
    """债券行情：按常用字段返回债券实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/bond", body)


async def cn(securities: list[dict], query_key: str | None = None) -> dict:
    """沪深京行情：按常用字段返回沪深京证券实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/cn", body)


async def forex(securities: list[dict], query_key: str | None = None) -> dict:
    """外汇行情：按常用字段返回外汇实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/forex", body)


async def fund(securities: list[dict], query_key: str | None = None) -> dict:
    """基金行情：按常用字段返回基金实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/fund", body)


async def future(securities: list[dict], query_key: str | None = None) -> dict:
    """期货行情：按常用字段返回期货实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/future", body)


async def hk(securities: list[dict], query_key: str | None = None) -> dict:
    """港股行情：按常用字段返回港股实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/hk", body)


async def index(securities: list[dict], query_key: str | None = None) -> dict:
    """指数行情：按常用字段返回指数实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/index", body)


async def quote(securities: list[dict], fields: list[int]) -> dict:
    """自选字段行情：按指定字段查询实时行情。同一次请求中的证券须属于同一市场。"""
    return await client.post(
        "/v1/market/realtime/quote", {"fields": fields, "securities": securities}
    )


async def trading_status(code: str, market: str) -> dict:
    """市场时间轴（兼容入口）：旧路径兼容入口，实际返回市场时间轴，不含证券当前交易状态。新调用请使用 /v1/market/calendar/timeline。"""
    return await client.post(
        "/v1/market/realtime/trading-status", {"code": code, "market": market}
    )


async def uk(securities: list[dict], query_key: str | None = None) -> dict:
    """英股行情：按常用字段返回英股实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/uk", body)


async def us(securities: list[dict], query_key: str | None = None) -> dict:
    """美股行情：按常用字段返回美股实时行情。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/realtime/us", body)
