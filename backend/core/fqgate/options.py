#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 期权（/v1/market/options/*）。"""
from core.fqgate import client


async def contracts(code: str, market: str) -> dict:
    """期权合约列表：根据标的证券返回可查询的期权合约。"""
    return await client.post(
        "/v1/market/options/contracts", {"code": code, "market": market}
    )


async def data(securities: list[dict], query_key: str | None = None) -> dict:
    """期权合约行情：返回期权合约行情。须传入期权合约代码，而非标的证券代码。"""
    body: dict = {"securities": securities}
    if query_key is not None:
        body["query_key"] = query_key
    return await client.post("/v1/market/options/data", body)


async def products() -> dict:
    """期权品种目录：返回可查询的期权品种及其标的信息。具体合约请通过期权合约列表查询。"""
    return await client.post("/v1/market/options/products", {})
