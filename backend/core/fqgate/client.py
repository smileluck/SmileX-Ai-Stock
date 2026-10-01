#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate HTTP 基础客户端。

base_url 从 DataSourceConfigProvider 的 FQGate 网关配置读取（默认
http://127.0.0.1:17281，可在数据源管理面板修改）。所有请求经
core.datasource.gateway.call_external_async 走统一限流/熔断/统计，
带 X-Request-Timeout-Ms 头（服务端查询预算 30s）。

响应为统一信封 {"code": 0, "message", "data", "warnings"}，code != 0 即抛错；
post() 返回 data 部分。data.records 为「分段 → 记录 → 字段」嵌套数组，
字段是同花顺协议数字编号，值可能是裸值或 {"value": ...} /
{"type": "invalid"|"no_update"} 包装，用 field_value / flatten_records 解包。
"""
import logging
from typing import Any

import httpx

from core.datasource.config import DataSourceConfigProvider
from core.datasource.gateway import call_external_async

logger = logging.getLogger(__name__)

SOURCE = "fqgate"
# 服务端行情查询预算 30s
SERVER_TIMEOUT_MS = "30000"


def field_value(v: Any) -> Any:
    """字段值解包：裸值直返，{"value": ...} 取值，{"type": "invalid"|"no_update"} 返回 None"""
    if isinstance(v, dict):
        if v.get("type") in ("invalid", "no_update"):
            return None
        return v.get("value")
    return v


def flatten_records(data: dict) -> list[dict]:
    """展平 data.records 的「分段 → 记录」嵌套结构为记录列表"""
    records = (data or {}).get("records") or []
    flat: list[dict] = []
    for segment in records:
        if isinstance(segment, list):
            flat.extend(r for r in segment if isinstance(r, dict))
        elif isinstance(segment, dict):
            flat.append(segment)
    return flat


async def new_client() -> httpx.AsyncClient:
    """按当前网关配置创建 httpx 客户端；base_url 未配置时抛错"""
    cfg = await DataSourceConfigProvider.get_fqgate_gateway()
    base_url = str(cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("FQGate base_url 未配置")
    return httpx.AsyncClient(base_url=base_url, timeout=35)


async def post(
    path: str, body: dict | None = None, client: httpx.AsyncClient | None = None
) -> dict:
    """POST 并校验统一信封，返回 data。传入 client 时复用连接（调用方负责关闭）"""
    owns_client = client is None
    client = client or await new_client()
    try:
        resp = await call_external_async(
            SOURCE,
            client.post,
            path,
            json=body or {},
            headers={"X-Request-Timeout-Ms": SERVER_TIMEOUT_MS},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(
                f"FQGate {path} 返回错误: {payload.get('code')} {payload.get('message')}"
            )
        return payload.get("data") or {}
    finally:
        if owns_client:
            await client.aclose()


async def get(path: str, timeout_s: float | None = None) -> dict:
    """GET 并校验统一信封，返回 data（如 /v1/market/health）。

    timeout_s 缺省时取数据源配置 timeout_s 与 35s 的较小值。"""
    if timeout_s is None:
        cfg = await DataSourceConfigProvider.get_source_config(SOURCE)
        timeout_s = min(float(cfg.get("timeout_s", 32)), 35.0)
    gw = await DataSourceConfigProvider.get_fqgate_gateway()
    base_url = str(gw.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("FQGate base_url 未配置")
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_s) as client:
        resp = await call_external_async(SOURCE, client.get, path)
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"FQGate {path} 返回错误: {payload.get('message')}")
    return payload.get("data") or {}


async def delete(path: str, body: dict | None = None) -> dict:
    """DELETE 并校验统一信封，返回 data（body 可选，如自选股删除）"""
    client = await new_client()
    try:
        resp = await call_external_async(
            SOURCE,
            client.request,
            "DELETE",
            path,
            json=body or {},
            headers={"X-Request-Timeout-Ms": SERVER_TIMEOUT_MS},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(
                f"FQGate {path} 返回错误: {payload.get('code')} {payload.get('message')}"
            )
        return payload.get("data") or {}
    finally:
        await client.aclose()
