#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
出站数据源网关

统一管理后端所有外部数据源（东财/新浪/baostock/FQGate 等）的出站调用：
- registry: 数据源静态注册表
- config: 每源限流/熔断配置（sys_config 表 + 内存缓存）
- throttle: 并发/间隔/超时/熔断控制
- stats: 用量统计（内存聚合 + 定时刷盘）
- gateway: 统一调用入口 call_external / call_external_async
"""
