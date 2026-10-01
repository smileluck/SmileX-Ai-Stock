#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate TAS 期货成交明细（/v1/market/history/tas-transactions）。"""
from core.fqgate import client


async def tas_transactions(
    code: str,
    count: int,
    fields: list[int],
    market: str,
    date: str | None = None,
    end_time: int | None = None,
    trace_detail: bool | None = None,
) -> dict:
    """TAS 期货成交明细：查询支持 TAS（结算价交易）的期货成交明细。

    code 须为从期货目录取得且支持 TAS 的实际合约代码（先通过字段 144
    确认 TAS 标识）。date 为交易日（通常 YYYYMMDD），省略或空字符串时
    由行情服务确定；end_time 为 Unix 秒时间戳（非 HHMMSS），省略或为 0
    时不指定。fields 只接受 TAS 字段编号，不接受普通逐笔成交字段名称。
    空记录表示当前行情服务未返回数据。"""
    body: dict = {"code": code, "count": count, "fields": fields, "market": market}
    if date is not None:
        body["date"] = date
    if end_time is not None:
        body["end_time"] = end_time
    if trace_detail is not None:
        body["trace_detail"] = trace_detail
    return await client.post("/v1/market/history/tas-transactions", body)
