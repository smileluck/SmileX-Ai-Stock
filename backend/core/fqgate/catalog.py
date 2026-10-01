#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 证券与板块（/v1/market/catalog/*）。"""
from core.fqgate import client


async def block(block_id: int, limit: int = 50, offset: int = 0) -> dict:
    """板块详情：根据板块目录中的编号返回板块信息，支持分页。"""
    return await client.post(
        "/v1/market/catalog/block",
        {"block_id": block_id, "limit": limit, "offset": offset},
    )


async def block_constituents(
    link_code: str, limit: int = 50, offset: int = 0
) -> dict:
    """板块成分证券：返回指定板块的成分证券，支持分页。请使用板块详情中的完整板块代码。"""
    return await client.post(
        "/v1/market/catalog/block-constituents",
        {"link_code": link_code, "limit": limit, "offset": offset},
    )


async def bond(limit: int = 50, offset: int = 0) -> dict:
    """债券目录：返回可查询的债券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/bond", {"limit": limit, "offset": offset}
    )


async def complete_code(
    code: str | None = None, codes: list | None = None
) -> dict:
    """证券代码补全：支持补全一个或多个证券代码，code 与 codes 两种输入方式不能同时使用。"""
    body: dict = {}
    if code is not None:
        body["code"] = code
    if codes is not None:
        body["codes"] = codes
    return await client.post("/v1/market/catalog/complete-code", body)


async def forex(limit: int = 50, offset: int = 0) -> dict:
    """外汇目录：返回可查询的外汇品种目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/forex", {"limit": limit, "offset": offset}
    )


async def fund_etf(limit: int = 50, offset: int = 0) -> dict:
    """ETF 目录：返回可查询的 ETF 目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/fund-etf", {"limit": limit, "offset": offset}
    )


async def fund_etf_t0(limit: int = 50, offset: int = 0) -> dict:
    """T+0 ETF 目录：返回可 T+0 交易的 ETF 目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/fund-etf-t0", {"limit": limit, "offset": offset}
    )


async def futures(limit: int = 50, offset: int = 0) -> dict:
    """期货合约目录：返回可查询的期货合约目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/futures", {"limit": limit, "offset": offset}
    )


async def index(limit: int = 50, offset: int = 0) -> dict:
    """指数目录：返回可查询的指数目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/index", {"limit": limit, "offset": offset}
    )


async def market_block(market: str, limit: int = 50, offset: int = 0) -> dict:
    """板块目录：返回指定市场的板块目录，支持分页。"""
    return await client.post(
        "/v1/market/catalog/market-block",
        {"market": market, "limit": limit, "offset": offset},
    )


async def nasdaq(limit: int = 50, offset: int = 0) -> dict:
    """纳斯达克证券目录：返回可查询的纳斯达克证券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/nasdaq", {"limit": limit, "offset": offset}
    )


async def related_securities(
    kind: str, securities: list[dict] | None = None
) -> dict:
    """关联证券：返回 A 股与 H 股对应证券、期货关联证券或期货与股票关联目录。

    kind 取值：ah_counterpart / futures_linked_securities / futures_stock_relation_content。
    securities 为需要查询的证券；查询关联目录时不需要填写。"""
    body: dict = {"kind": kind}
    if securities is not None:
        body["securities"] = securities
    return await client.post("/v1/market/catalog/related-securities", body)


async def related_securities_list(
    code: str,
    market: str,
    limit: int = 20,
    offset: int = 0,
    sort_direction: str | None = None,
    sort_field: int = 55,
) -> dict:
    """证券关联列表：返回证券关联的板块等项目，记录可能使用 URFI、URFA 等板块市场代码。

    支持分页，单页默认最多 20 条，默认按名称字段 55 降序排列。
    sort_direction 取值 ascending / descending；sort_field 必须大于 0。"""
    body: dict = {
        "code": code,
        "market": market,
        "limit": limit,
        "offset": offset,
        "sort_field": sort_field,
    }
    if sort_direction is not None:
        body["sort_direction"] = sort_direction
    return await client.post("/v1/market/catalog/related-securities/list", body)


async def search_symbols(pattern: str, need_market: str | None = None) -> dict:
    """搜索证券：按证券名称或代码片段搜索证券。need_market 限定搜索的市场代码，省略时不限定市场。"""
    body: dict = {"pattern": pattern}
    if need_market is not None:
        body["need_market"] = need_market
    return await client.post("/v1/market/catalog/search-symbols", body)


async def security_blocks(code: str, market: str) -> dict:
    """证券所属板块：返回指定证券所属的板块。"""
    return await client.post(
        "/v1/market/catalog/security-blocks", {"code": code, "market": market}
    )


async def security_industries(securities: list[dict]) -> dict:
    """证券所属行业：返回一只或多只证券所属的行业。允许包含不同市场的证券。"""
    return await client.post(
        "/v1/market/catalog/security-industries", {"securities": securities}
    )


async def stock_b(limit: int = 50, offset: int = 0) -> dict:
    """B 股证券目录：返回可查询的 B 股证券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/stock-b", {"limit": limit, "offset": offset}
    )


async def stock_bj(limit: int = 50, offset: int = 0) -> dict:
    """北交所证券目录：返回可查询的北交所证券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/stock-bj", {"limit": limit, "offset": offset}
    )


async def stock_cn(limit: int = 50, offset: int = 0) -> dict:
    """沪深证券目录：返回可查询的沪深证券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/stock-cn", {"limit": limit, "offset": offset}
    )


async def stock_hk(limit: int = 50, offset: int = 0) -> dict:
    """港股证券目录：返回可查询的港股证券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/stock-hk", {"limit": limit, "offset": offset}
    )


async def stock_uk(limit: int = 50, offset: int = 0) -> dict:
    """英股证券目录：返回可查询的英股证券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/stock-uk", {"limit": limit, "offset": offset}
    )


async def stock_us(limit: int = 50, offset: int = 0) -> dict:
    """美股证券目录：返回可查询的美股证券目录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/stock-us", {"limit": limit, "offset": offset}
    )


async def ths_concept(limit: int = 50, offset: int = 0) -> dict:
    """同花顺概念目录：返回同花顺概念板块记录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/ths-concept", {"limit": limit, "offset": offset}
    )


async def ths_industry(limit: int = 50, offset: int = 0) -> dict:
    """同花顺行业目录：返回同花顺行业板块记录，单页默认返回 50 条。"""
    return await client.post(
        "/v1/market/catalog/ths-industry", {"limit": limit, "offset": offset}
    )
