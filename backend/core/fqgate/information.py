#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 资讯（/v1/market/information/*）。"""
from core.fqgate import client


async def categories() -> dict:
    """资讯分类：返回资讯来源及其分类层级。"""
    return await client.post("/v1/market/information/categories", {})


async def document(
    code: str,
    market: str,
    text_id: int,
    last_text_time: int | None = None,
    summary: bool | None = None,
) -> dict:
    """证券资讯文档：按资讯分类编号返回指定证券的资讯内容；例如 14341 为公告。text_id 不是单篇文档编号，可选择仅返回摘要。last_text_time 仅返回该时间之后的内容，首次查询可省略。"""
    body = {"code": code, "market": market, "text_id": text_id}
    if last_text_time is not None:
        body["last_text_time"] = last_text_time
    if summary is not None:
        body["summary"] = summary
    return await client.post("/v1/market/information/document", body)


async def major_events(
    code: str, market: str, start_date: str, end_date: str
) -> dict:
    """证券重大事件：返回指定证券在日期范围内的重大事件。日期格式 YYYYMMDD。"""
    return await client.post(
        "/v1/market/information/major-events",
        {
            "code": code,
            "market": market,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


async def news(
    code: str,
    market: str,
    last_text_time: int | None = None,
    summary: bool | None = None,
    text_id: int | None = None,
) -> dict:
    """证券资讯：返回证券资讯列表及阅读地址。返回的 XML 在每条资讯的 id 后补充 url，其他字段保持不变。可将上一次响应中的资讯时间作为 last_text_time 继续读取，省略时从最新内容开始读取。summary 省略时为 true；text_id 省略时查询 14356 市场新闻（例如 14339 为个股资讯、14341 为公告）。"""
    body = {"code": code, "market": market}
    if last_text_time is not None:
        body["last_text_time"] = last_text_time
    if summary is not None:
        body["summary"] = summary
    if text_id is not None:
        body["text_id"] = text_id
    return await client.post("/v1/market/information/news", body)


async def stock_comments(code: str, market: str) -> dict:
    """个股评论：返回指定证券最近二十四小时的个股评论。"""
    return await client.post(
        "/v1/market/information/stock-comments", {"code": code, "market": market}
    )


async def ipo_pending() -> dict:
    """待申购新股：返回当前可申购或即将申购的新股，无需登录行情账户。"""
    return await client.post("/v1/market/information/ipo-pending", {})


async def ipo_today() -> dict:
    """今日新股：返回今日发行的新股，无需登录行情账户。"""
    return await client.post("/v1/market/information/ipo-today", {})
