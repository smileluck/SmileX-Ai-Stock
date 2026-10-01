#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 财务数据（/v1/market/history/financial）。"""
from core.fqgate import client


async def financial(
    code: str,
    fields: list[int],
    market: str,
    count: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """财务历史：返回指定证券的财务历史记录。

    支持按记录数量（count）或日期范围查询，两者互斥；省略两者时返回全部
    可用记录。日期格式 YYYYMMDD，start_date 与 end_date 须同时填写。"""
    body: dict = {"code": code, "fields": fields, "market": market}
    if count is not None:
        body["count"] = count
    if start_date is not None:
        body["start_date"] = start_date
    if end_date is not None:
        body["end_date"] = end_date
    return await client.post("/v1/market/history/financial", body)
