<!-- last-updated: 2026-09-15 -->
# MCP 使用指南

## 概述

本项目集成了 MCP（Model Context Protocol）工具平台，支持 AI 助手通过标准化协议调用后端工具。MCP 服务已从主应用拆分为独立组件 `mcp-platform/`（FastMCP + Streamable HTTP，uvicorn ASGI）；`backend/` 只保留管理接口（`/admin/sys/mcp/*`），通过 HTTP 代理到独立服务的 `/manage/*` 端点。

## 架构

```
AI 客户端（Claude / Cursor / Trae 等）
        │
        │ MCP 协议（Streamable HTTP，默认 http://127.0.0.1:9001/mcp）
        ▼
  mcp-platform 独立服务（run.py → uvicorn）
        │
        ├── 工具发现与注册（mcp_server/registry.py）
        ├── 鉴权上下文传播（mcp_server/context.py）
        ├── 上游 HTTP 回调主应用（mcp_server/http_client.py）
        ├── 管理端点 /manage/*（mcp_server/manage.py）
        └── 工具实现（mcp_server/tools/*.py）
```

## 目录结构

```
mcp-platform/
├── run.py                    # 独立服务入口（uvicorn，含优雅关闭）
├── pyproject.toml            # 独立依赖（mcp[cli]、httpx、uvicorn）
└── mcp_server/
    ├── __init__.py           # 包标记
    ├── config.py             # MCPSettings：环境变量 / .env 配置
    ├── registry.py           # 工具注册表 + @register_tool 装饰器 + 自动发现
    ├── server.py             # FastMCP 服务器创建与 ASGI 挂载
    ├── context.py            # 鉴权上下文（contextvars 传播）
    ├── http_client.py        # 上游 HTTP 客户端（工具回调主应用 API）
    ├── result.py             # 结果辅助函数
    ├── template.py           # 工具代码模板生成器
    ├── manage.py             # /manage/* 管理端点（Starlette）
    ├── types.py              # 类型定义
    └── tools/                # 工具实现目录
        └── __init__.py
```

## 配置

独立服务自身配置定义于 `mcp-platform/mcp_server/config.py:MCPSettings`，通过环境变量或 `.env` 文件加载：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `NAME` | `"SmileX MCP Server"` | MCP 服务器名称 |
| `HOST` | `"127.0.0.1"` | 服务监听地址 |
| `PORT` | `9001` | 服务监听端口 |
| `UPSTREAM_BASE_URL` | `"http://127.0.0.1:8000"` | 主应用 URL（工具回调用） |
| `AUTH_HEADER` | `"Authorization"` | 鉴权 Header 名称 |
| `REQUEST_TIMEOUT` | `30` | HTTP 请求超时（秒） |

backend 侧另有一份管理用配置 `backend/core/config/settings_model.py:MCPModel`（`HOST`/`PORT` 默认指向 `127.0.0.1:9000`，`PROCESS_META_FILE` 等），管理接口用它拼接独立服务地址与拉起进程；两侧地址需保持一致。

## 启动与生命周期

MCP 只以独立服务方式运行（主应用 `backend/main.py` 不再挂载 MCP 子应用）：

- 手动启动：`cd mcp-platform && python run.py`，默认监听 `http://127.0.0.1:9001`（MCP 协议端点 `/mcp`）
- 生命周期管理：backend 管理接口 `POST /admin/sys/mcp/start`、`POST /admin/sys/mcp/stop`、`POST /admin/sys/mcp/status`（`backend/modules/admin/endpoints/sys/mcp.py`），经 `MCPService`（`backend/modules/admin/services/sys/mcp_service.py`）代理到独立服务的 `/manage/*` 端点
- 适用场景：需要隔离 MCP 工具的资源消耗；开发环境同样推荐该方式

## 创建 MCP 工具

### 方式一：通过模板自动生成

调用管理接口 `POST /admin/sys/mcp/add`，传入工具定义：

```json
{
  "name": "query-user",
  "description": "根据用户名查询用户信息",
  "params": [
    { "name": "username", "description": "用户名", "type": "string", "required": true },
    { "name": "page", "description": "页码", "type": "number", "required": false, "default": 1 }
  ],
  "response": [
    { "key": "id", "type": "number", "description": "用户ID" },
    { "key": "username", "type": "string", "description": "用户名" }
  ]
}
```

系统会在 `mcp_server/tools/` 目录自动生成 `query_user.py` 文件（backend 管理接口经 `/manage/tools/create` 转发给独立服务生成），包含完整的工具类框架。生成后需要编辑 `handle()` 方法实现业务逻辑。

### 方式二：手动编写

在 `mcp-platform/mcp_server/tools/` 目录下创建新文件，按以下模板编写（真实示例见 `mcp_server/tools/query_dictionaries.py`）：

```python
from mcp_server.registry import register_tool, ToolParam
from mcp_server.context import McpContext
from mcp_server.result import text_result, text_result_with_json, text_result_error
from mcp_server.types import TextContent


@register_tool
class QueryUser:
    @classmethod
    def tool_name(cls) -> str:
        return "query-user"

    @classmethod
    def tool_description(cls) -> str:
        return "根据用户名查询用户信息"

    @classmethod
    def tool_params(cls) -> list[ToolParam]:
        return [
            ToolParam(name="username", description="用户名", type="string", required=True),
        ]

    async def handle(self, arguments: dict, context: McpContext) -> list[TextContent]:
        username = arguments.get("username")
        # 实现业务逻辑
        # 可使用 McpHttpClient 回调主应用 API
        result = {"username": username, "id": 123}
        return text_result_with_json(result)
```

### 工具注册机制

1. 使用 `@register_tool` 装饰器标记工具类
2. 工具类必须实现 `McpTool` 协议的四个方法：`tool_name()`、`tool_description()`、`tool_params()`、`handle()`
3. 服务器启动时通过 `discover_tools()` 自动扫描 `mcp_server/tools/` 目录下的所有模块
4. 已注册工具可通过 `POST /admin/sys/mcp/list`（或独立服务的 `GET /manage/tools/list`）查看

### 参数类型

| type 值 | Python 类型 | 说明 |
|---------|------------|------|
| `string` | `str` | 字符串 |
| `number` | `float` | 数值 |
| `boolean` | `bool` | 布尔值 |
| `array` | `list` | 数组 |
| `object` | `dict` | 对象 |

## 结果返回

使用 `mcp_server/result.py` 中的辅助函数构建返回值：

```python
from mcp_server.result import text_result, text_result_with_json, text_result_error

# 纯文本
return text_result("操作成功")

# JSON 格式（推荐）
return text_result_with_json({"id": 1, "name": "test"})

# 错误信息
return text_result_error("用户不存在")
```

## 鉴权与上下文

### 请求上下文

MCP 通过 `contextvars` 在异步调用链中传递鉴权信息：

- AI 客户端请求时携带 `x-token` 或 `Authorization` Header
- `McpContext.from_headers()` 自动提取 Token
- 工具的 `handle()` 方法通过 `context` 参数获取 Token

### 回调主应用

工具如需调用主应用 API，使用 `McpHttpClient`（`mcp_server/http_client.py`）：

```python
from mcp_server.http_client import McpHttpClient

class MyTool:
    async def handle(self, arguments: dict, context: McpContext) -> list[TextContent]:
        client = McpHttpClient()
        # 自动携带当前请求的鉴权 Token
        result = await client.get("/admin/sys/user/list", params={"page": 1})
        return text_result_with_json(result)
```

`McpHttpClient` 自动：
- 从 `mcp_request_ctx` 获取当前请求的 Token
- 拼接 `UPSTREAM_BASE_URL` 前缀
- 设置鉴权 Header

## 管理接口

backend 侧管理接口定义于 `backend/modules/admin/endpoints/sys/mcp.py`，路径前缀为 `/admin/sys/mcp`；`MCPService` 将大部分操作代理到独立服务的 `/manage/*` 端点：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/admin/sys/mcp/add` | POST | 从模板创建工具（代理 `/manage/tools/create`） |
| `/admin/sys/mcp/list` | POST | 获取已注册工具列表（代理 `/manage/tools/list`） |
| `/admin/sys/mcp/routes` | POST | 获取 MCP 路由信息 |
| `/admin/sys/mcp/test` | POST | 测试工具执行（代理 `/manage/tools/test`） |
| `/admin/sys/mcp/status` | POST | 获取服务器状态 |
| `/admin/sys/mcp/start` | POST | 启动独立服务 |
| `/admin/sys/mcp/stop` | POST | 停止独立服务（代理 `/manage/shutdown`） |

### 测试工具

```json
POST /admin/sys/mcp/test
{
  "tool_name": "query-user",
  "arguments": { "username": "admin" }
}
```

## 新增工具的完整流程

1. 在 `mcp-platform/mcp_server/tools/` 目录创建工具文件（手动或通过模板 API）
2. 实现 `McpTool` 协议的四个方法
3. 编辑 `handle()` 方法实现业务逻辑
4. 启动/重启独立服务（`python run.py` 或 `POST /admin/sys/mcp/start`）
5. 调用 `POST /admin/sys/mcp/list` 验证工具已注册
6. 调用 `POST /admin/sys/mcp/test` 测试工具执行
7. 在 AI 客户端中配置 MCP 服务地址

## 时间参数规范

MCP 工具如需接收时间参数，遵循项目统一的时间格式约定（详见 `aiDoc/contracts/boundary.md`）：

- **入参格式**：ISO 8601 带时区偏移，如 `2026-05-21T16:39:23+08:00`
- **解析方式**：
  ```python
  dt = datetime.fromisoformat(time_str)
  result = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
  ```
- **禁止**：直接对带时区偏移的字符串使用 `.replace(tzinfo=timezone.utc)`

## 相关文件

| 文件 | 职责 |
|------|------|
| `mcp-platform/run.py` | 独立服务入口（uvicorn） |
| `mcp-platform/mcp_server/registry.py` | 工具注册表、自动发现、`McpTool` 协议 |
| `mcp-platform/mcp_server/server.py` | FastMCP 服务器创建与 ASGI 挂载 |
| `mcp-platform/mcp_server/config.py` | 独立服务配置（`MCPSettings`） |
| `mcp-platform/mcp_server/context.py` | 鉴权上下文 |
| `mcp-platform/mcp_server/http_client.py` | 上游 HTTP 客户端 |
| `mcp-platform/mcp_server/result.py` | 结果辅助函数 |
| `mcp-platform/mcp_server/template.py` | 工具代码生成器 |
| `mcp-platform/mcp_server/manage.py` | `/manage/*` 管理端点 |
| `mcp-platform/mcp_server/tools/` | 工具实现目录 |
| `backend/modules/admin/endpoints/sys/mcp.py` | backend 侧管理接口 |
| `backend/modules/admin/services/sys/mcp_service.py` | 管理服务层（代理独立服务） |
| `backend/modules/admin/schemas/sys/mcp.py` | 管理 Schema |
| `backend/core/config/settings_model.py` | backend 侧 MCP 配置模型（`MCPModel`） |

## 日志模块

系统提供登录日志和操作日志两个模块，前端搜索表单已统一为标准折叠网格布局（`NCollapse` + `NGrid` + `NFormItemGi`）。

### 后端 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/admin/sys/login-log/list` | GET | 分页查询登录日志 |
| `/admin/sys/login-log/batch/delete` | DELETE | 批量删除登录日志 |
| `/admin/sys/login-log/clear` | DELETE | 清理过期登录日志（默认 30 天） |
| `/admin/sys/login-log/{log_id}` | GET/DELETE | 查看/删除单条登录日志 |
| `/admin/sys/operation-log/list` | GET | 分页查询操作日志 |
| `/admin/sys/operation-log/export` | GET | 导出操作日志 |
| `/admin/sys/operation-log/batch/delete` | DELETE | 批量删除操作日志 |
| `/admin/sys/operation-log/clear` | DELETE | 清理过期操作日志（默认 30 天） |
| `/admin/sys/operation-log/{log_id}` | GET/DELETE | 查看/删除单条操作日志 |

### 前端组件

| 组件 | 路径 |
|------|------|
| 登录日志列表 | `frontend/src/views/log/login-log/index.vue` |
| 登录日志搜索 | `frontend/src/views/log/login-log/modules/login-log-search.vue` |
| 操作日志列表 | `frontend/src/views/log/operation-log/index.vue` |
| 操作日志搜索 | `frontend/src/views/log/operation-log/modules/operation-log-search.vue` |
| 操作日志详情 | `frontend/src/views/log/operation-log/modules/operation-log-detail-drawer.vue` |
