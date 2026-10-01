#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate Level-2 行情（/v1/market/level2/*）。"""
from core.fqgate import client


async def best_ask_queue(
    code: str,
    market: str,
    require_data: bool | None = None,
    semantic: bool = True,
    start: int | None = None,
    trade_date: str | None = None,
) -> dict:
    """卖方委托队列：返回指定证券卖一档的逐项委托数量及队列信息。
    start 为队列起始位置（省略时从当前卖一档开始），trade_date 为字段说明对应的交易日（YYYYMMDD）。"""
    body: dict = {"code": code, "market": market, "semantic": semantic}
    if require_data is not None:
        body["require_data"] = require_data
    if start is not None:
        body["start"] = start
    if trade_date is not None:
        body["trade_date"] = trade_date
    return await client.post("/v1/market/level2/best-ask-queue", body)


async def best_bid_queue(
    code: str,
    market: str,
    require_data: bool | None = None,
    semantic: bool = True,
    start: int | None = None,
    trade_date: str | None = None,
) -> dict:
    """买方委托队列：返回指定证券买一档的逐项委托数量及队列信息。
    start 为队列起始位置（省略时从当前买一档开始），trade_date 为字段说明对应的交易日（YYYYMMDD）。"""
    body: dict = {"code": code, "market": market, "semantic": semantic}
    if require_data is not None:
        body["require_data"] = require_data
    if start is not None:
        body["start"] = start
    if trade_date is not None:
        body["trade_date"] = trade_date
    return await client.post("/v1/market/level2/best-bid-queue", body)


async def cancellations_buy(
    code: str,
    fields: list,
    market: str,
    range: dict | None = None,
    require_data: bool | None = None,
    semantic: bool = True,
    trade_date: str | None = None,
) -> dict:
    """买入撤单：返回指定证券买入方向的撤单明细，查询范围 range 可使用 all 或 recent。
    fields 推荐填字段名称：order_no、latest_price、price、volume、amount、request_time、cancel_time。"""
    body: dict = {"code": code, "fields": fields, "market": market, "semantic": semantic}
    if range is not None:
        body["range"] = range
    if require_data is not None:
        body["require_data"] = require_data
    if trade_date is not None:
        body["trade_date"] = trade_date
    return await client.post("/v1/market/level2/cancellations/buy", body)


async def cancellations_sell(
    code: str,
    fields: list,
    market: str,
    range: dict | None = None,
    require_data: bool | None = None,
    semantic: bool = True,
    trade_date: str | None = None,
) -> dict:
    """卖出撤单：返回指定证券卖出方向的撤单明细，查询范围 range 可使用 all 或 recent。
    fields 推荐填字段名称：order_no、latest_price、price、volume、amount、request_time、cancel_time。"""
    body: dict = {"code": code, "fields": fields, "market": market, "semantic": semantic}
    if range is not None:
        body["range"] = range
    if require_data is not None:
        body["require_data"] = require_data
    if trade_date is not None:
        body["trade_date"] = trade_date
    return await client.post("/v1/market/level2/cancellations/sell", body)


async def depth(securities: list[dict]) -> dict:
    """十档盘口：返回指定证券的买一至买十、卖一至卖十价格与委托数量，并保留完整行情字段。
    securities 为证券列表，如 [{"code": "600519", "market": "USHA"}]。"""
    return await client.post("/v1/market/level2/depth", {"securities": securities})


async def enhanced_transactions(
    code: str,
    count: int,
    fields: list[int],
    market: str,
    date: str | None = None,
    end_time: int | None = None,
    trace_detail: bool | None = None,
) -> dict:
    """TAS 成交明细兼容入口：实际查询 TAS 期货成交明细，不提供 A 股增强逐笔成交。
    新请求请使用 /v1/market/history/tas-transactions。code 为支持 TAS 的实际合约代码（如 sc2610），
    fields 为 TAS 字段编号（不接受普通逐笔成交字段名称），end_time 为 Unix 秒时间戳（省略或为 0 时不指定）。"""
    body: dict = {
        "code": code,
        "count": count,
        "fields": fields,
        "market": market,
    }
    if date is not None:
        body["date"] = date
    if end_time is not None:
        body["end_time"] = end_time
    if trace_detail is not None:
        body["trace_detail"] = trace_detail
    return await client.post("/v1/market/level2/enhanced-transactions", body)


async def order_detail_by_sequence(
    code: str, market: str, order_sequence: int
) -> dict:
    """逐笔委托详情：根据证券和逐笔委托序号返回对应的委托详情。"""
    return await client.post(
        "/v1/market/level2/order-detail-by-sequence",
        {"code": code, "market": market, "order_sequence": order_sequence},
    )


async def orders(
    code: str,
    fields: list,
    market: str,
    range: dict | None = None,
    require_data: bool | None = None,
    semantic: bool = True,
    trade_date: str | None = None,
) -> dict:
    """逐笔委托：返回指定证券的逐笔委托，查询范围 range 可使用 all 或 recent。
    fields 推荐填字段名称：order_no、price、side、volclass、volume、amount、order_time、request_time；
    结果中的方向位于 semantic_records[].derived.side。"""
    body: dict = {"code": code, "fields": fields, "market": market, "semantic": semantic}
    if range is not None:
        body["range"] = range
    if require_data is not None:
        body["require_data"] = require_data
    if trade_date is not None:
        body["trade_date"] = trade_date
    return await client.post("/v1/market/level2/orders", body)


async def transactions(
    code: str,
    fields: list,
    market: str,
    count: int | None = None,
    end_time: int | None = None,
    range: dict | None = None,
    require_data: bool | None = None,
    semantic: bool = True,
    start_time: int | None = None,
    trade_date: str | None = None,
) -> dict:
    """逐笔成交：返回指定证券的逐笔成交。两种查询方式不可混用：
    按数量填 count 和 end_time（end_time=0 查最新，count 单次最多 2000 条，不能与 start_time 同用）；
    按时间区间填 start_time 和 end_time（不填 count）。时间均为 UTC Unix 秒。
    旧 range 参数保留兼容，不能与 count/start_time/end_time 混用。trade_date（YYYYMMDD）只补充可读时间，不筛选记录。
    fields 推荐填字段名称：price、side、volume、trade_time 等；volclass=1 为 sell，5 为 buy。"""
    body: dict = {"code": code, "fields": fields, "market": market, "semantic": semantic}
    if count is not None:
        body["count"] = count
    if end_time is not None:
        body["end_time"] = end_time
    if range is not None:
        body["range"] = range
    if require_data is not None:
        body["require_data"] = require_data
    if start_time is not None:
        body["start_time"] = start_time
    if trade_date is not None:
        body["trade_date"] = trade_date
    return await client.post("/v1/market/level2/transactions", body)
