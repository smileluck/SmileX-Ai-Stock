#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 盯盘（/v1/market/stream、/v1/market/watch/*）。

本组的 /v1/market/stream 是 WebSocket 端点，httpx 不支持 ws 协议，
只提供 ws_url() 生成连接地址；/v1/market/watch/short-line-events 为
SSE 长连接，由 short_line_events() 以异步生成器逐行返回。
"""
from collections.abc import AsyncGenerator

import httpx

from core.fqgate import client


async def ws_url() -> str:
    """标准订阅接口的 WebSocket 连接地址。

    把网关配置的 base_url 中 http(s) 协议换成 ws(s)，拼上
    /v1/market/stream 路径（如 ws://127.0.0.1:17281/v1/market/stream）。

    用法：用 websockets 等 ws 客户端连接该地址，一条连接可连续发送
    多条 JSON 订阅指令，无需为不同证券或数据类型重复建连。指令格式::

        {"action": "subscribe", "kind": "quote", "market": "USHA", "code": "600519"}
        {"action": "subscribe", "kind": "short_line", "market": "USZA"}
        {"action": "unsubscribe", "subscription_id": 1}
        {"action": "ping"}

    除短线精灵外指令均使用 kind、market、code；逐笔成交/逐笔委托/撤单
    的 fields 推荐字段名称，其他行情类型用字段编号；常规行情 fields
    可选，资金流订阅必须填写字段编号；大单资金流可用 money（元，默认
    1000000）设金额下限。每次订阅成功返回独立 subscription_id。

    服务端消息按 event 区分：subscribed / unsubscribed / data / notice
    / pong；data 消息中 subscription_ids 对应订阅编号，内容位于 data。
    """
    http_client = await client.new_client()
    try:
        base = str(http_client.base_url).rstrip("/")
    finally:
        await http_client.aclose()
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    return base + "/v1/market/stream"


async def short_line_events(market: str) -> AsyncGenerator[str, None]:
    """短线精灵实时订阅（SSE）：持续接收指定市场的新异动，不含历史记录。

    低级流式能力：GET /v1/market/watch/short-line-events 是 SSE 长连接，
    没有新异动时连接保持打开；本函数逐行 yield 原始文本行，调用方自行
    解析 SSE 结构（每条事件使用统一的行情响应结构）。
    """
    http_client = await client.new_client()
    # 长连接流式读取，去掉读超时，仅保留连接超时
    http_client.timeout = httpx.Timeout(None, connect=35.0)
    try:
        async with http_client.stream(
            "GET", "/v1/market/watch/short-line-events", params={"market": market}
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                yield line
    finally:
        await http_client.aclose()
