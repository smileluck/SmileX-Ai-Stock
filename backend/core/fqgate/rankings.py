#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 排行榜（/v1/market/rankings/*、/v1/market/level2/bid-ask-rank）。"""
from core.fqgate import client


async def bid_ask_rank(code: str, market: str) -> dict:
    """买卖盘排名：返回指定证券的买卖盘排名数据，需要 Level-2 权限。
    需要持续接收变化时，请使用实时订阅中的 bid_ask_rank 类型。"""
    return await client.post(
        "/v1/market/level2/bid-ask-rank", {"code": code, "market": market}
    )


async def block(
    block_id: int,
    sort_begin: int,
    sort_count: int,
    sort_direction: str,
    sort_field: int,
    function_period: int | None = None,
) -> dict:
    """板块排行：按指定行情字段返回一个板块内的证券排行。

    block_id 为板块目录返回的板块编号；sort_begin 从 0 开始；
    sort_direction 取 ascending / descending；sort_field 常用值：
    199112 涨跌幅、19 成交额、48 五分钟涨速、900232 人气排名。
    function_period 仅年报类字段使用，普通行情字段请省略。"""
    body = {
        "block_id": block_id,
        "sort_begin": sort_begin,
        "sort_count": sort_count,
        "sort_direction": sort_direction,
        "sort_field": sort_field,
    }
    if function_period is not None:
        body["function_period"] = function_period
    return await client.post("/v1/market/rankings/block", body)


async def market(
    market: str,
    sort_begin: int,
    sort_count: int,
    sort_direction: str,
    sort_field: int,
    function_period: int | None = None,
) -> dict:
    """市场排行：按指定行情字段返回一个市场内的证券排行。

    market 如沪市 A 股 USHA、深市 A 股 USZA；sort_begin 从 0 开始；
    sort_direction 取 ascending / descending；sort_field 常用值：
    199112 涨跌幅、19 成交额、48 五分钟涨速、900232 人气排名。
    function_period 仅年报类字段使用，普通行情字段请省略。"""
    body = {
        "market": market,
        "sort_begin": sort_begin,
        "sort_count": sort_count,
        "sort_direction": sort_direction,
        "sort_field": sort_field,
    }
    if function_period is not None:
        body["function_period"] = function_period
    return await client.post("/v1/market/rankings/market", body)


async def securities(
    securities: list[dict],
    sort_direction: str,
    sort_field: int,
    sort_begin: int = 0,
    sort_count: int = 50,
    function_period: int | None = None,
) -> dict:
    """指定证券排行：按指定行情字段对证券列表排序，返回所选范围内的结果。

    securities 为参加排序的证券列表（{"code", "market"}）；sort_begin
    默认 0，sort_count 默认 50；sort_direction 取 ascending / descending；
    sort_field 为排序依据的行情字段编号，如 55 名称、10 最新价。
    function_period 仅年报类字段使用，普通行情字段请省略。"""
    body = {
        "securities": securities,
        "sort_begin": sort_begin,
        "sort_count": sort_count,
        "sort_direction": sort_direction,
        "sort_field": sort_field,
    }
    if function_period is not None:
        body["function_period"] = function_period
    return await client.post("/v1/market/rankings/securities", body)
