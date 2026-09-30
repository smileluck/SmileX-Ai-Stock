#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据源管理相关 Schema
"""
from typing import Any

from pydantic import BaseModel, Field


class SourceConfigUpdate(BaseModel):
    """单源限流/熔断配置更新（部分字段，未提供的保持原值）"""

    source: str = Field(..., description="数据源标识（core.datasource.registry 的 key）")
    config: dict[str, Any] = Field(
        ...,
        description="配置项子集：enabled(bool) / max_concurrency(int) / min_interval_ms(int) / "
                    "timeout_s(number) / failure_threshold(int) / cooldown_s(int) / "
                    "circuit_mode(auto|force_open|force_closed)",
    )


class FqgateGatewayUpdate(BaseModel):
    """FQGate 网关连接配置更新"""

    base_url: str = Field(..., description="FQGate 本机地址，如 http://127.0.0.1:17281")
