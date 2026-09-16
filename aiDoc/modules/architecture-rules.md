<!-- last-updated: 2026-09-15 -->
# 架构与模块组织规则（architecture rules）

> 本文件只承载**跨组件**的架构约束与各组件的范式归属；各组件内部的详细分层规则链接到对应专文，不在此复制。

## 总原则

- 架构边界是硬约束：禁止跨层调用、禁止跨模块抄近路、禁止跨组件绕过契约直接依赖对方内部实现
- 每层/每组件只通过下游的公开接口交互
- 组件清单与判定依据以机器产物 [../relations/code-index.md](../relations/code-index.md) 为准

## 组件一：`backend/`（web-backend，FastAPI）

分层服务范式，依赖方向严格为 `Endpoint -> Service -> Model`：

- 模块目录：`backend/modules/<name>/`，含 `endpoints/`、`services/`、`schemas/`、`deps/` 与聚合路由 `router.py`
- 路由注册：模块路由在 `backend/main.py` 中通过 `app.include_router()` 注册
- 数据库模型集中在 `backend/database/models/`，迁移由 Alembic 管理（`backend/alembic/`）
- 可扩展功能走插件体系：`backend/plugins/`，插件生命周期见 [plugin-development.md](plugin-development.md)
- 各层基类、字段声明、异常处理、分页与错误码分配的完整规则见 [backend-layer-rules.md](backend-layer-rules.md)；新增模块的分步流程见 [module-development.md](module-development.md)

## 组件二：`frontend/`（web-frontend，Vue 3 + Vite）

组件结构范式，pnpm monorepo：

- 页面：`frontend/src/views/<name>/`；API 封装：`frontend/src/service/api/`；类型：`frontend/src/typings/`；状态：`frontend/src/store/`
- 共享能力优先复用 workspace 子包 `frontend/packages/`（`@sa/axios`、`@sa/hooks`、`@sa/materials`、`@sa/utils` 等），禁止在应用层重造
- 详细规范见 [../frontend/frontend-rules.md](../frontend/frontend-rules.md) 与 [../frontend/frontend-utils.md](../frontend/frontend-utils.md)

## 组件三：`mcp-platform/`（web-backend，uvicorn ASGI / FastMCP）

独立部署的 MCP 工具服务：

- 入口：`mcp-platform/run.py`（uvicorn 启动，含 SIGINT/SIGTERM 优雅关闭）
- 服务实现：`mcp-platform/mcp_server/`，工具在 `mcp_server/tools/` 下按 `registry.py` 的注册机制自动发现
- 该服务不直接访问数据库；需要主应用数据时通过 HTTP 回调 `backend/`（上游地址由 `mcp_server/config.py` 的 `UPSTREAM_BASE_URL` 配置，默认 `http://127.0.0.1:8000`）
- 使用与工具开发细节见 [mcp-guide.md](mcp-guide.md)

## 跨组件契约

| 边界 | 契约 | 权威文档 |
|---|---|---|
| `frontend/` ↔ `backend/` | HTTP JSON API：统一响应结构、分页结构、Status 桥接 | [../contracts/boundary.md](../contracts/boundary.md) |
| `mcp-platform/` → `backend/` | HTTP 上游回调（鉴权头透传） | [mcp-guide.md](mcp-guide.md) |

新增跨组件交互时，必须先在上表对应的契约文档中登记契约，再实现两侧代码。
