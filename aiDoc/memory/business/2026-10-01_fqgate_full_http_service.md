# FQGate HTTP 全量封装为独立服务能力（core/fqgate）+ 数据源能力清单面板展示

## 需求描述

用户要求按 FQGate 官方文档（http://127.0.0.1:17281/docs，OpenAPI v1.0.5，16-17 组约 100 端点）将 FQGate 数据源接入改为 HTTP 调用，并：
1. 全量封装所有端点为独立服务能力，供后续扩展和使用；
2. 数据源注册表为每个源补充结构化能力描述，并在数据源管理面板展示；
3. 现有 `_fqgate.py` 调用链迁移到新服务，`_fqgate.py` 降为薄适配层（对外签名与行为不变）。

## 状态

已完成

## 涉及范围

### 后端

- 新核心包 `backend/core/fqgate/`（与 `core/datasource/` 平级，基础设施客户端，非业务模块）：
  - `client.py`：`post/get/delete`，统一信封校验（`code != 0` 抛 RuntimeError），所有请求经 `call_external_async("fqgate", ...)` 走网关限流/熔断/统计，带 `X-Request-Timeout-Ms: 30000`；`field_value`/`flatten_records` 解包工具；`post` 支持传入共享 `httpx.AsyncClient` 复用连接
  - `capabilities.py`：`CAPABILITY_GROUPS`（17 组 × 端点 {path, method, summary, description, auth_required, level2}），能力元数据唯一真源
  - 分组模块：calendar(2)/catalog(24)/session(16，含 GET health、DELETE session)/auction(2)/kline(4)/tick(5)/financial(1)/tas(1)/information(7，资讯+新股)/level2(9)/rankings(4)/options(3)/realtime(12)/selection(2)/topics(1)；`stream.py` 特殊：`ws_url()`（http→ws 地址换算 + 订阅指令说明）、`short_line_events()` SSE 异步迭代器（低级流式能力）
  - 除已验证链路外，各函数直接返回信封 data，不臆造字段映射
- `modules/stock/services/_fqgate.py` 降为 A 股业务薄适配层，公开函数签名不变（resolve_security/to_fq_security/health/fetch_daily_bars(_by_security)/fetch_trading_days/fetch_quotes_by_securities/fetch_spot_quotes）；保留代码→市场映射、字段编号解析、preclose/pct_chg 折算等 A 股语义
- **交易日历改用专用接口** `POST /v1/market/calendar/trading-days`（无需登录），600519 日K 推导留作降级兜底
- `core/datasource/registry.py`：每个源新增 `capabilities: [{key, label}]`；FQGate 由 CAPABILITY_GROUPS 生成，其余 11 源按现有调用点人工归纳
- `datasource_service.list_sources` 返回携带 capabilities

### 前端

- `typings/api/datasource.d.ts`：`SourceInfo` 新增 `capabilities: Capability[]`（`{key, label}`）
- `views/env-config/datasource/index.vue`：源状态表新增「支持能力」列（NTag 展示前 3 个，超出折叠进 NPopover）
- locale 键 `page.manage.datasource.capabilities`（zh 支持能力 / en Capabilities）+ `typings/app.d.ts` Schema 同步

## 约束与备注

- 不触碰 `sys_mcp_server` 已种子的 FQGate MCP 服务（Agent 工具链独立通道）
- catalog.complete_code 的批量字段名 `codes` 为推断（spec 未给出批量入参名），使用时需实测确认
- stream.py 的 short_line_events 以 query param 传 market（spec 未列参数），若实际不符需按真实行为调整
- locale 新键必须同步 `typings/app.d.ts` Schema（既有纪律）
- **顺带修复存量隐患**：`/v1/market/realtime/quote` 要求同一次请求证券属于同一市场（混沪深报 1003），`fetch_quotes_by_securities` 改为按 market 分组逐组请求后合并；实测沪深混合批量报价通过

## 相关文件

- `backend/core/fqgate/`（client.py、capabilities.py、17 个分组模块）
- `backend/modules/stock/services/_fqgate.py`
- `backend/core/datasource/registry.py`
- `backend/modules/datasource/services/datasource_service.py`
- `frontend/src/typings/api/datasource.d.ts`、`frontend/src/views/env-config/datasource/index.vue`
- `frontend/src/locales/langs/{zh-cn,en-us}.ts`、`frontend/src/typings/app.d.ts`
- `aiDoc/contracts/boundary.md`（数据源管理模块契约追加）

## 记录日期

2026-10-01
