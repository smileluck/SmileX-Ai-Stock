#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 选股（/v1/market/selection/*）。"""
from core.fqgate import client


async def wencai_base(condition: str, max_results: int | None = None) -> dict:
    """问财条件选股：根据选股条件返回匹配结果。使用前须登录行情账户。"""
    body: dict = {"condition": condition}
    if max_results is not None:
        body["max_results"] = max_results
    return await client.post("/v1/market/selection/wencai-base", body)


async def wencai_nlp(condition: str) -> dict:
    """问财自然语言选股：使用自然语言描述选股条件并返回匹配结果，无需登录行情账户。"""
    return await client.post(
        "/v1/market/selection/wencai-nlp", {"condition": condition}
    )
