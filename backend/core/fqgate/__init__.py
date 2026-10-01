#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""FQGate 本机行情网关 HTTP 全量封装。

按 FQGate OpenAPI（v1.0.5）分 17 组封装约 100 个端点，供各业务模块复用：
- client: 基础客户端（统一信封校验、限流/熔断经 core.datasource.gateway）
- capabilities: 能力元数据（数据源注册表/面板展示的唯一真源）
- 其余模块按端点分组：calendar/catalog/session/auction/kline/tick/financial/
  tas/information/level2/rankings/options/realtime/selection/stream/topics

除少数已验证链路的字段解析（见 modules/stock/services/_fqgate.py 业务适配层）外，
各分组函数直接返回 FQGate 响应信封中的 data，不做业务字段映射。
"""
from core.fqgate import (  # noqa: F401
    auction,
    calendar,
    catalog,
    client,
    financial,
    information,
    kline,
    level2,
    options,
    rankings,
    realtime,
    selection,
    session,
    stream,
    tas,
    tick,
    topics,
)
from core.fqgate.capabilities import CAPABILITY_GROUPS  # noqa: F401
