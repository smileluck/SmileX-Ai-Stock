# 应用内接入 FQGate MCP 服务 + 环境配置目录新增「MCP 服务」管理页

## 需求描述

FQGate 自带 MCP 服务（Streamable HTTP，127.0.0.1:17281/mcp，32 个 fqgate_market_* 工具）。
应用户要求：在应用中接入该 MCP，并在「环境配置」目录中增加 MCP 服务的配置和管理。

## 状态

已完成

## 涉及范围

### 后端

- 迁移 `0051_add_mcp_server.py`：
  - 新表 `sys_mcp_server`（code 唯一/name/url/headers JSON/enabled/timeout_s/remark + 标准审计列）
  - 种子 FQGate（id=2942406616008048，code=fqgate，url=http://127.0.0.1:17281/mcp，enabled）
  - 菜单 `env-config_mcp-server`（id=2942406616008044，parent=env-config 目录 8042，sort=86）+ 按钮 `mcp:list/manage/test`（8045-8047）
- 新模型 `database/models/sys/mcp_server.py`
- 新核心层 `core/mcp/client.py`：Streamable HTTP 短连接薄封装（initialize→执行→关闭），list_tools 返回 McpServerTools（含 instructions/serverInfo），call_tool 文本拼接截断 8000 字符，统一 wait_for 超时
- 新模块 `modules/mcpserver/`（前缀 `/admin/mcp-server`）：list（分页）/add/update/status/delete/test/tools，权限 `mcp:*`
- Agent 动态工具接入：
  - `tool_registry.py` 加 `_DYNAMIC` + register_dynamic_tool/clear_dynamic_tools；execute() 合并查找，VAR_KEYWORD 闭包透传全部参数
  - `modules/agent/tools/mcp_tools.py`：每次对话前 register_mcp_tools(db)，TTL 300s 进程内缓存 tools/list，工具命名 `mcp__<code>__<去重后工具名>`（如 mcp__fqgate__market_klines），单 server 失败只跳过；server instructions 拼进 system prompt「外部数据源使用规则」
  - `agent_service.py`：resolve_model 后注册动态工具，SYSTEM_PROMPT 补 mcp__ 前缀工具说明

### 前端

- 新页面 `views/env-config/mcp-server/`（列表+启停开关+测试+查看工具 Modal+新增/编辑抽屉）
- API `service/api/mcp-server.ts`，类型 `typings/api/mcp-server.d.ts`（Api.McpServer.*）
- locale 键 `route.env-config_mcp-server`（zh MCP 服务 / en MCP Servers）+ `page.manage.mcpServer.*`；同步 typings/app.d.ts Schema 与 elegant-router.d.ts（RouteMap + LastLevelRouteKey）

## 约束与备注

- 只支持 Streamable HTTP 传输的 MCP server；不支持 stdio/SSE 类型；不做工具级开关
- 策略/分析执行器不接 MCP（只接 Agent 对话）
- FastAPI 拒绝「空前缀+空路径」组合：创建接口用 POST /add 而非 POST ""（同 factor 模块踩过的坑）
- 前端 headers 字段为 JSON 文本域，提交前 JSON.parse 校验且必须是普通对象
- enabled 为原生 boolean（搜索区 '1'/'2' → boolean 桥接沿用 enableStatusToBoolean）
- `.mcp.json` 也加了 fqgate 条目（供 AI 编程助手用，与应用内接入独立）

## 验证

- 迁移 0051 upgrade 成功，psql 确认种子（server + 4 菜单行）
- curl 验证：list 分页 / test（success, 36ms, 32 工具）/ tools（32 个）
- Agent 端到端：POST /admin/agent/chat 问「贵州茅台最新价」，SSE 出现 mcp__fqgate__market_market_data_cn 调用，回答 1258.62 元并按 FQGate instructions 末行注明数据来源
- 前端 pnpm typecheck 与存量 10 错误基线完全一致，无新增

## 相关文件

- `backend/alembic/versions/0051_add_mcp_server.py`、`backend/database/models/sys/mcp_server.py`
- `backend/core/mcp/client.py`、`backend/modules/mcpserver/`
- `backend/modules/agent/tools/mcp_tools.py`、`backend/modules/agent/services/tool_registry.py`、`agent_service.py`
- `frontend/src/views/env-config/mcp-server/`、`frontend/src/service/api/mcp-server.ts`、`frontend/src/typings/api/mcp-server.d.ts`

## 记录日期

2026-10-01
