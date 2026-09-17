<!-- last-updated: 2026-09-16 -->
# 前后端边界与数据契约

## 责任边界

| 层面 | 后端负责 | 前端负责 |
|------|----------|----------|
| 数据验证 | 请求参数校验、业务规则验证 | 表单验证、输入格式化 |
| 业务逻辑 | 全部业务逻辑 | 仅页面交互逻辑 |
| 数据存储 | 数据库读写、缓存管理 | 本地存储（localStorage） |
| 响应结构 | 统一响应格式 | 响应解析与展示 |
| 状态管理 | 会话状态（Redis） | 页面状态（Pinia） |
| 路由 | API 路由注册 | 页面路由与守卫 |

共享行为通过明确的 API 契约实现，不依赖隐式耦合。

---

## 统一响应结构

### 普通响应

```json
{
  "code": 200,
  "msg": "成功",
  "data": { ... },
  "request_id": "uuid-string",
  "err_code": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | `number` | HTTP 状态码 |
| `msg` | `string` | 响应消息 |
| `data` | `T \| null` | 响应数据 |
| `request_id` | `string \| null` | 请求追踪 ID |
| `err_code` | `number \| null` | 业务错误码 |

### 分页响应

```json
{
  "code": 200,
  "msg": "成功",
  "data": {
    "records": [ ... ],
    "page": 1,
    "page_size": 10,
    "total": 100,
    "total_pages": 10
  },
  "request_id": "uuid-string",
  "err_code": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `records` | `T[]` | 当前页数据 |
| `page` | `number` | 当前页码（从 1 开始） |
| `page_size` | `number` | 每页条数（最大 200） |
| `total` | `number` | 总记录数 |
| `total_pages` | `number` | 总页数 |

---

## 字段命名

- API 请求和响应中字段名统一使用 `snake_case`
- 前端 TypeScript 类型定义与后端字段名保持一致
- 示例：`created_at`、`page_size`、`user_name`

---

## Status 字段桥接

这是前后端类型转换中最关键的约定。

### 转换流程

```
前端（展示/编辑）          后端（存储/逻辑）
"1" / "2"                True / False
    │                        │
    │ 前端发送请求            │ 数据库存储
    │ enableStatusToBoolean()│
    ├───────────────────────>│ bool
    │                        │
    │ 前端接收响应            │ BaseRespEntity 序列化
    │                        │ @field_serializer("status")
    │<───────────────────────┤ "1" / "2"
```

### 后端处理

- **存储类型**：`bool`（`True` = 启用，`False` = 禁用）
- **反序列化**（前端→后端）：`BoolField` 使用 `parse_bool` 处理
  - `"1"` / `"true"` / `"yes"` → `True`
  - `"2"` / `"false"` / `"no"` → `False`
  - 空值 → `None`
- **序列化**（后端→前端）：`BaseRespEntity` 的 `@field_serializer("status")`
  - `True` → `"1"`
  - `False` → `"2"`
- 定义位置：`modules/common/schemas/base.py`

### 前端处理

- **TypeScript 类型**：`EnableStatus`（`"1" | "2"`）
- **发送请求时**：使用 `enableStatusToBoolean()` 将 `"1"`/`"2"` 转为 `boolean`
- **接收响应时**：后端已自动转换为 `"1"`/`"2"` 字符串
- **转换函数**：`frontend/src/utils/status.ts`

### `is_system` 字段

与 `status` 字段处理方式相同：`BaseRespEntity` 自动序列化 `is_system`（`True` → `"1"`，`False` → `"2"`）。

---

## 时间字段桥接

### 后端 → 前端（响应序列化）

| 层面 | 类型 | 格式 |
|------|------|------|
| 后端数据库 | `datetime`（带时区） | UTC 存储 |
| 后端序列化 | `string` | `Asia/Shanghai`，`YYYY-MM-DD HH:mm:ss` |
| 前端接收 | `string` | `YYYY-MM-DD HH:mm:ss` |

序列化由 `BaseEntity` 的 `json_encoders` 自动处理（`modules/common/schemas/base.py`）。

### 前端 → 后端（请求参数）

| 层面 | 类型 | 格式示例 |
|------|------|----------|
| 前端选择 | `number`（时间戳） | NDatePicker 返回毫秒时间戳 |
| 前端发送 | `string` | `2026-05-21T16:39:23+08:00`（本地时间 + 时区偏移） |
| 后端解析 | `datetime` | `fromisoformat()` → `astimezone(UTC)` → UTC datetime |

**强制规则**：

1. **前端发送时间参数时，必须携带时区偏移**：使用 `dayjs(val).format()` 生成 `YYYY-MM-DDTHH:mm:ssZ` 格式（如 `+08:00`），禁止使用 `new Date(val).toISOString()` —— 后者会转为 UTC 导致与用户选择不一致
2. **后端解析时间参数时，必须区分有无时区**：
   ```python
   dt = datetime.fromisoformat(time_str)
   result = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
   ```
   禁止直接使用 `.replace(tzinfo=timezone.utc)` —— 对带时区偏移的字符串会丢失转换

**原因**：用户在前端选择 `2026-05-21 16:39:23`，API 传参也应体现为 `16:39:23+08:00`，而非 UTC 时间 `08:39:23Z`。

---

## 数据权限（行级可见性）

### 后端

- `SysRole.data_scope` 字段：枚举 `DataScopeEnum`（`ALL` / `DEPT_AND_SUB` / `DEPT_ONLY` / `SELF`），默认 `SELF`，序列化为字符串
- `SysUser.dept_id` 字段：可空外键，关联 `sys_dept.id`
- `DataScopeService.get_effective_scope(db, user)`：聚合用户角色的 data_scope，返回 `DataScopeEnum | None`（None=不限，超管/含 ALL 角色）
- `DataScopeService.get_permitted_dept_ids(db, user, scope)`：返回 `set[int] | None`
  - `None` → 不加任何 dept 过滤（ALL/超管）
  - 空集合 → Service 走 `where(id == user.id)`（SELF）
  - 非空集合 → Service 走 `where(dept_id.in_(...))`（DEPT_AND_SUB / DEPT_ONLY）

### 前端

- `Api.SystemManage.DataScope` 类型：`'ALL' | 'DEPT_AND_SUB' | 'DEPT_ONLY' | 'SELF'`
- 角色编辑表单使用 `NRadioGroup` 单选数据范围；提交时直接传字符串（后端 pydantic 接收 `DataScopeEnum`）
- 用户编辑表单使用 `NTreeSelect` 选择部门，提交 `dept_id: number | null`

### 接入新模块的方式

业务模块要接入数据权限，需在 Service 的 `build_*_query()` 增加：
```python
def build_xxx_query(
    query_params,
    *,
    data_scope: DataScopeEnum | None = None,
    permitted_dept_ids: set[int] | None = None,
    current_user_id: int | None = None,
) -> Select:
    # ... 原有过滤 ...
    if data_scope == DataScopeEnum.SELF:
        base_query = base_query.where(Xxx.created_by == current_user_id)
    elif permitted_dept_ids is not None:
        base_query = base_query.where(Xxx.dept_id.in_(permitted_dept_ids))
    return base_query
```

Endpoint 注入 `current_user` 后调用 `DataScopeService` 算出 scope 与 permitted_dept_ids，传给 Service。

---

## 开放API（商户 HMAC 签名鉴权）

`/open/*` 路由面向第三方系统，**不走** 后台管理员 JWT 鉴权与操作日志中间件（`OperationLogMiddleware` 只作用于 `/admin/*`），改用商户 `app_id/app_secret` 的 HMAC-SHA256 签名鉴权。后台管理侧（`/admin/sys/merchant/*`）仍是普通 JWT + 权限码管理。

### 签名请求头

| Header | 说明 |
|---|---|
| `X-App-Id` | 商户 AppId |
| `X-Timestamp` | 秒级 Unix 时间戳（允许偏移见 `OPEN_API__TIMESTAMP_TOLERANCE_SECONDS`，默认 300s） |
| `X-Nonce` | 客户端随机串，8-64 字符，TTL 内（`OPEN_API__NONCE_TTL`，默认 600s）不可复用 |
| `X-Signature` | HMAC-SHA256 hex 小写 |

### Canonical String（客户端必须严格复现）

6 段以 `\n` 连接，顺序固定，body 为空时第 6 段为空串（末尾保留 `\n`）：

```
METHOD \n PATH \n timestamp \n nonce \n app_id \n sha256(body).hexdigest()
```

- `PATH` 用 `request.url.path`，**不含 query string**
- 完整契约见 `backend/core/security/openapi/signature.py` 模块 docstring

### 商户凭据

- `app_id` 公开标识；`app_secret` 在库中以 Fernet 加密存储（验签需原始值，不能单向哈希），密钥 `OPEN_API__SECRET_ENCRYPT_KEY`
- 明文 `app_secret` **仅在创建/重置密钥时一次性返回**，前端弹窗强提示保存；此后不可查询，只能重置
- 后台响应 `SysMerchantResponseData` 继承 `BaseRespEntity`，`status` 已序列化为 `"1"/"2"`，前端列表无需再做 bool 转换

### 错误码（`err_code`，区间 11021-11030）

`/open/*` 鉴权错误经独立的 `OpenApiError` + `openapi_error_handler` 处理，映射到语义正确的 4xx HTTP 状态（响应结构仍是统一 `{code, msg, data, request_id, err_code}`，只是 `code` = HTTP 状态码而非 500）。日志用 `warning` 级，不污染 5xx 错误率统计。

| err_code | HTTP | 含义 |
|---|---|---|
| 11021 | 401 | 缺少必要的签名请求头 |
| 11022 | 401 | 请求时间戳超出允许范围 |
| 11023 | 400 | Nonce 非法（格式/长度） |
| 11024 | 401 | 请求不可重放（Nonce 已被使用） |
| 11025 | 401 | AppId 不存在 |
| 11026 | 403 | 商户已禁用 |
| 11027 | 401 | 签名校验失败 |

后台管理侧的 11028（商户不存在）/ 11029（商户编码已存在）/ 11030（AppId 冲突）仍走 `CustomError`（HTTP 500 + body err_code），与 captcha/rate-limit 等现有模块一致，前端按 `err_code` 判断。

---

## 文件预览鉴权（preview token）

`GET /admin/sys/file/{id}/preview` 供 `<img>/<video>` 直接通过 src 访问，浏览器不会携带 `Authorization` 头，因此**不能复用 access token**（否则令牌会进入 URL 日志/Referer 造成泄露）。改为两步：

1. **换令牌**：前端先调 `POST /admin/sys/file/{id}/preview-token`（需登录 + `sys:file:list` 权限），后端签发**短期（默认 5 分钟）、绑定 file_id** 的预览令牌（JWT，`scope=preview`），返回 `{ preview_token, expires_in }`。
2. **访问预览**：前端以 `GET /admin/sys/file/{id}/preview?token=<preview_token>` 访问；后端校验 `scope=preview` 且 token 内 `file_id` 与 URL 一致，否则返回 401/403。

| 项 | 值 |
|---|---|
| 换令牌接口 | `POST /admin/sys/file/{id}/preview-token` |
| 响应 data | `{ preview_token: string, expires_in: number }`；有效期由后端 `JWT__PREVIEW_TOKEN_EXPIRES` 配置（默认 300 秒） |
| 预览接口鉴权 | query `token`，需 `scope=preview` + file_id 绑定 |
| 前端封装 | `fetchGetPreviewToken`、`getFilePreviewUrl(fileId, previewToken)`（`frontend/src/service/api/file.ts`）；组件 `views/manage/file/modules/file-preview-modal.vue` 打开时异步换 token |
| 已知妥协 | 预览令牌有效期内即使用户登出仍可用（短 exp 缓解；强一致需 preview_file 内查 Redis session） |

前端调用点必须**先换 token 再拼 URL**，禁止直接把 access token 放进 preview URL。

---

## 国际化（i18n / `Accept-Language`）

后端响应消息（统一返回结构里的 `msg`、异常消息、Pydantic 校验消息）支持多语言，按请求头 `Accept-Language` 决定返回语言。

### 契约

| 侧 | 职责 |
|---|---|
| 前端 | 每个后端请求带 `Accept-Language: <locale>` 头，取值来自 vue-i18n 当前 locale（`getLocale()`，值为 `zh-CN` / `en-US`），在 `frontend/src/service/request/index.ts` 的 `onRequest` 拦截器统一注入 |
| 后端 | 最外层纯 ASGI 中间件 `RequestContextMiddleware` 解析 `Accept-Language`（支持 RFC 质量值与语言前缀匹配，如 `zh`↔`zh-CN`），写入请求级语言 ContextVar；未传或无匹配走 `I18N.DEFAULT_LANGUAGE`（默认 `zh-CN`） |
| 前端 | 后端 `msg` 已按请求语言返回，前端**原样展示**（`$dialog`/`$message` 直接用 `response.data.msg`），无需前端再翻译后端消息 |

### 支持语言与扩展

- 当前支持 `zh-CN`、`en-US`，文案目录为 `backend/core/i18n/locales/<locale>.yaml`（嵌套 YAML，加载时拍平为 dotted key）
- 新增语言：在 `locales/` 下新增 `<locale>.yaml`（key 与 `zh-CN.yaml` 1:1 对齐），并把该 locale 追加到配置 `I18N.SUPPORTED_LANGUAGES`，无需改代码
- 默认/回退语言由 `I18N.DEFAULT_LANGUAGE` / `I18N.FALLBACK_LANGUAGE` 控制（`.env` 用 `I18N__DEFAULT_LANGUAGE` 等覆盖）

### 新增/修改一条后端消息

1. 在 `zh-CN.yaml` 与 `en-US.yaml` 同步增删 key（两文件 key 必须一致）
2. 代码中用 `from core.i18n import t` 后 `t("ns.key")` 或带占位符 `t("ns.key", name=value)`（模板用 `{name}` 命名占位符）
3. `CustomResponseCode` / `CustomErrorCode` 枚举成员元组第二位即 i18n key，`.msg` 自动按当前请求语言翻译；`.code` 数字不变
4. 异常类用 `default_msg_key` 声明默认文案 key，未显式传 `msg` 时按当前请求语言翻译

### 明确不翻译（保持原文）

- `logger.xxx("...")` 日志串（运维侧诊断，翻译会割裂日志检索）
- Pydantic `Field(description=...)`、FastAPI `summary=`（仅 Swagger 展示）
- 启动/基础设施层错误（DB 连接池、URL 构建器、雪花 ID、配置加载器等 `RuntimeError`/启动期 `ValueError`）——多由 `generic_exception_handler` 兜底为固定文案，不会把中文原文透传到响应体

---

## 变更规则

- 破坏性接口变更（字段名/类型/结构改变）必须记录变更说明
- Swagger 注释必须与真实实现保持一致
- 前端 API 封装统一放在 `frontend/src/service/api/`
- 跨栈变更必须同步更新 `aiDoc/contracts/` 下的文档

## 完成前检查清单

- [ ] 后端响应结构与前端类型定义匹配
- [ ] 字段名 `snake_case` 一致
- [ ] Status 字段桥接正确（`enableStatusToBoolean()` + `BaseRespEntity` 序列化）
- [ ] 时间字段格式正确（`YYYY-MM-DD HH:mm:ss`）
- [ ] Swagger 注释与实现一致
- [ ] 分页参数和返回格式符合 `ResponsePageModel` 规范
---

## AI 分析策略模块契约（2026-08-16，2026-08-18 更新）

- 前缀 `/admin/strategy`；权限码：`strategy:manage`（策略 CRUD）、`strategy:run`（手动执行）、`strategy:position:list`（持仓/统计/跟踪日志/手动触发跟踪）、`strategy:position:close`（手动平仓）
- 策略 CRUD：`GET/POST /strategies`、`PUT/DELETE /strategies/{id}`，分页查询走统一分页结构；`execute_periods` 为 JSON 数组（`pre_market/morning/noon/tail/post_close`），`stock_pool` 为 `{codes: string[]}`（空则 AI 全市场自选）
- 2026-08-17 新增策略分类：`category` 字符串（`pre_market_auction/noon/tail/blue_chip/general`，自建默认 `general`）+ `is_preset` bool（系统预置标记）；列表接口新增 `category` 过滤参数；迁移 0016 预置 10 条策略（默认停用，允许编辑/删除），蓝筹白马两类带固定股票池
- 2026-08-18 执行异步化 + 信号由交易引擎执行：`POST /strategies/{id}/run` 改为异步提交（毫秒级返回 `{run_id, status: "running"}`，LLM 分析在后台任务中进行，同策略并发守卫错误码 11508）；执行记录 `GET /strategies/{id}/runs` 的 `status` 由 bool 改为字符串三态 `running/success/failed`，`opened_count/closed_count` 由交易引擎执行信号时累加（分析完成时为 0）；买卖信号落新表 `business_strategy_signal`（pending/executed/skipped/failed/expired），由每分钟任务 `strategy.trade_engine`（cron `* * * * * 9-15 * * mon-fri`）按新浪实时价执行模拟买卖 + 持仓跟踪（接管原 */5 `strategy.position_track`，已下线）；执行 user prompt 注入策略 `stop_loss_pct/take_profit_pct` 风控比例
- 2026-08-29 回撤止盈（迁移 0025）：策略与创建/更新请求新增 `trailing_drawdown_pct`（0/不填=不启用，默认 5）；持仓响应新增 `trailing_drawdown_pct`（建仓时快照）与 `peak_price`（持仓期间最高价）；`sell_reason` 新增枚举值 `trailing_stop`（现价自峰值回撤超阈值且仍浮盈时平仓）；回撤达阈值一半时触发 AI 盘中复核（run_period=review）
- 持仓：`GET /positions`（`strategy_id/status/stock_code` 过滤 + 分页，`status`: holding/closed/cancelled）、`POST /positions/track`（手动触发跟踪）、`POST /positions/{id}/close`（手动平仓，body `{price?, reason?}`）、`GET /positions/{id}/tracks`、`GET /positions/stats`
- Agent 工具新增（策略/对话共用）：`get_index_history`（指数日 K 线）、`get_index_constituents`（沪深300/中证500 成分股，数据来自 BaoStock 同步任务 `stock.constituent_sync`，每交易日 17:10）
- 金额/比例均为 `number`（后端 Numeric → float），百分比数值不带 `%`；时间字段带时区 datetime
- 前端 API：`frontend/src/service/api/strategy.ts`，类型 `Api.Strategy.*`（`frontend/src/typings/api/strategy.d.ts`，含 `StrategyCategory`）

---

## AI 大盘/板块分析模块契约（2026-08-19）

- 前缀 `/admin/analysis`；权限码：`analysis:run`（手动触发生成，两菜单共享）、`analysis:list`（查询类接口，两菜单共享）；path 参数 `analysis_type`：`market`-大盘 / `sector`-板块，非法值错误码 11601
- 生成：`POST /{analysis_type}/run`（异步提交，毫秒级返回 `{run_id, status: "running"}`，LLM 在后台任务生成，同类型并发守卫错误码 11603）；查询：`GET /{analysis_type}/latest`（最新一条含报告原文，**无记录 `data` 为 `null`**——此类可空 data 接口 response_model 必须写 `ResponseModel[X | None]`，裸 `ResponseModel[X]` 下 `success(data=None)` 会撞泛型必填校验 → 500"服务器错误"，先例 scheduler `ResponseModel[dict | None]`）、`GET /{analysis_type}/runs`（分页历史，列表项不含 `ai_raw_response`）、`GET /runs/{run_id}`（详情，错误码 11602）
- 执行记录 `AnalysisRunItem`：`status` 字符串三态 `running/success/failed`（对齐策略 run）；`trigger_type`: `schedule`/`manual`；`parsed_result` 为 JSON 摘要——大盘 `{sentiment, score, summary, key_points[], tomorrow_outlook?}`，板块 `{rotation_summary, hot_boards: [{board_name, board_type, change_pct, viewpoint}], key_points[], tomorrow_outlook?}`，`tomorrow_outlook` 为 `{direction, summary}`（策略配置开启明日研判时才有，历史记录可能无此字段）；LLM 未按格式输出时 `parsed_result` 为 `null`（报告原文仍在 `ai_raw_response`，markdown 格式，开头可能带 ```json 摘要块，前端渲染前剥离）
- 分析策略配置（迁移 0022，新表 `business_analysis_config`，每类型一条；0023 加 `tomorrow_prompt_template` 列）：`GET /{analysis_type}/config`（无记录返回默认值 `{prompt_template: null, include_tomorrow: true, tomorrow_prompt_template: null}`，**data 始终非空**）、`PUT /{analysis_type}/config`（权限 `analysis:strategy`，body `{prompt_template?: string|null, include_tomorrow: boolean, tomorrow_prompt_template?: string|null}`，下次生成时生效）；prompt_template 注入 user prompt「分析策略要求」段，tomorrow_prompt_template 在研判开启时注入「明日研判策略要求」段（优先级高于内置框架；前端关闭研判时该字段随保存清空）
- 定时任务 `analysis.auto_generate`（cron `5 16 * * mon-fri`，收盘行情同步后）自动生成两类分析，同日同类型已有记录则跳过；手动触发不受同日去重限制
- 菜单：`ai_market-analysis`（大盘分析）/`ai_sector-analysis`（板块分析），挂 AI 目录（8001）下 sort 4/5，迁移 0021（含 4 个 BUTTON 行承载 `analysis:list`/`analysis:run`，MENU 行的 permission 码仅展示用——`require_permission` 只校验 BUTTON 类型）
- 前端 API：`frontend/src/service/api/analysis.ts`，类型 `Api.Analysis.*`（`frontend/src/typings/api/analysis.d.ts`）；指数/资金流/板块排行复用 `stock-market.ts`/`stock-board.ts` 现有接口；共用报告面板 `frontend/src/views/ai/components/analysis-report-panel.vue`（最新记录 `running` 时 5s 轮询 `latest`，完成即停）

---

## 每日资讯分析 / 宏观指数 / 财报解读 契约（2026-08-29，迁移 0026）

### 每日资讯分析（analysis 模块扩展 news 类型）

- `analysis_type` 新增 `news`（每日资讯分析）；`session` 新增 `weekly`（周度复盘）。**类型×时段合法组合**：news 仅 `morning/weekly`，market/sector 仅 `close/morning`，非法组合错误码 11601
- 复用现有 analysis 全部接口（`/run`、`/latest`、`/runs`、`/runs/{id}`、config），无新表；morning 取近 24h 资讯 60 条、weekly 取近 7 天 120 条，注入中美宏观指数读数
- `parsed_result` 为 `{macro_industry_news: [{title, category, viewpoint, impact, source}], stock_news: [{title, stock_name, viewpoint, impact, source}], summary, key_points[]}`，两个分类数组各 ≤10 条
- 定时任务：`analysis.news_morning_generate`（cron `25,40 9 * * mon-fri`）、`analysis.news_weekly_generate`（cron `30,50 20 * * sun`，APScheduler 星期必须写 `sun`），同日去重逻辑与大盘/板块一致
- 菜单 `ai_news-analysis`（每日资讯分析），权限复用 `analysis:list`/`analysis:run`；前端 `views/ai/news-analysis/index.vue` 复用 `analysis-report-panel.vue`（news 类型渲染两个分类列表卡片，策略抽屉隐藏研判开关）

### 宏观指数（macro 新模块）

- 前缀 `/admin/macro`；权限码 `macro:list`（查询）、`macro:sync`（手动同步）；指标查询参数非法错误码 11621
- 接口：`GET /macro/indicators?country=CN|US&indicator=cpi|ppi|m0|m1|m2&limit`（period 升序序列，供图表）、`GET /macro/indicators/latest`（每个国家×指标最新一期）、`POST /macro/sync`（手动触发 akshare 抓取 + upsert，返回 `{sources, saved}`）
- 新表 `business_macro_indicator`：`country+indicator_code+period` 唯一 upsert；金额/增速均为 number
- 定时任务 `macro.sync_all`（cron `30 7 * * *`）；数据源 akshare：中国 `macro_china_cpi_monthly/macro_china_ppi_yearly/macro_china_money_supply`、美国 `macro_usa_cpi_monthly`
- **注入 AI 分析**：market（close/morning）与 news 分析的 user prompt 注入中美 CPI/PPI/M1/M2 最新读数独立段，LLM 调用失败时随资讯段一起摘除降级重试
- 菜单 `ai_macro`（宏观指数）；前端 `views/ai/macro/index.vue`（中美 tab + 指标卡片 + ECharts 走势）

### 企业财报解读（financial 新模块）

- 前缀 `/admin/financial`；权限码 `financial:list`（查询）、`financial:run`（触发解读）；错误码 11641-11644（report_not_found / report_fetch_failed / interpret_not_found / already_running）
- 接口：`GET /financial/reports/{stock_code}?limit`（库内财报指标，report_period 倒序）、`POST /financial/interpretations/{stock_code}`（异步提交解读：库内无财报自动补抓，返回 `{interpretation_id, status: "running"}`，同股票并发守卫 11644）、`GET /financial/interpretations?page&page_size&stock_code&quality_rating&forecast_direction`（分页记录）、`GET /financial/interpretations/detail/{id}`（详情含报告原文）、`GET/PUT /financial/config`（分析策略 prompt_template ≤2000 字，权限 financial:list / financial:run，0029）
- `parsed_result` 为 `{quality_rating, next_quality_rating, highlights[], risks[], forecast: {direction, summary, drivers[]}}`（drivers=下期盈利预测驱动因素 2-4 条，0029 起 prompt 强制产出）；`status` 三态 `running/success/failed`；`trigger_type`: `schedule`（持仓自动）/`manual`
- 列表/详情行附 `industry`（所属行业）与 `research_brief: {org_name, rating, published_date, forecast{年份:{eps,pe}}}`（该股最新券商研报摘要，每股取 published_date 最新一条，无研报时为 null；0029）
- 新表 `business_financial_report`（`stock_code+report_period` 唯一）与 `business_financial_interpretation`；数据源 akshare `stock_financial_analysis_indicator`（新浪财务指标，白名单列名容错匹配）
- 定时任务 `financial.auto_interpret`（cron `0 8 * * mon-fri`）：持仓 + 近30天策略信号标的，补抓财报后对最新报告期无成功解读的个股自动提交解读（同报告期去重）
- 菜单 `ai_financial-analysis`（财报分析）；前端 `views/ai/financial-analysis/index.vue`（代码查询 + 解读报告 + 指标表 + 历史列表）

### 券商研报中心（research 新模块，迁移 0027）

- 前缀 `/admin/research`；权限码 `research:list`（查询）、`research:sync`（手动同步）；错误码 11661-11662（stock_code_invalid / sync_failed）
- 接口：`GET /research/reports?page&page_size&stock_code&keyword&org_name&rating&start_date&end_date`（分页研报列表，published_date 倒序）、`GET /research/reports/stats?days=30`（概览统计）、`POST /research/reports/sync`（body `{stock_codes: []}`，不传自动收集持仓+近30天信号标的，空库用兜底热门池；返回 `{codes, saved, failed}`）
- 研报字段：`stock_code/stock_name/title/url(去重键)/org_name/rating/industry/published_date/forecast({年份:{eps,pe}})`；东财源无作者/目标价/摘要
- 新表 `business_research_report`（`url` 唯一 upsert）；数据源 akshare `stock_research_report_em`；定时任务 `research.sync_reports`（cron `0 */4 * * *`）
- **供 AI/策略消费**：Agent 工具 `get_research_reports(stock_code, days=90, limit=10)` 与 `get_report_consensus(stock_code, days=90)`（评级分布/覆盖机构数/最新评级时间线），已加入策略 SYSTEM_PROMPT 工具清单；预置策略「研报掘金」（general 类，pre_market 时段，股票池设单只个股即对该公司分析）
- 菜单 `ai_research-report`（研报中心，ID 8029-8031）；前端 `views/ai/research-report/index.vue`（统计卡片 + 评级分布 + 热门 TOP 点击筛选 + remote 分页列表）

### A股板块领涨股前三名 + 涨停池连板概率（2026-08-31，迁移 0028）

- `GET /admin/stock/board/list` 的 `BoardDailyItem` 新增 `leading_stocks: [{code, name, change_pct}] | null`（板块内涨幅前三降序，兜底数据源仅单只且 `code` 可为 null）；旧三字段 `leading_stock_*` 保留并由 top1 回填，前端优先渲染 `leading_stocks`，历史数据回退旧字段
- 数据来源：东财源按板块补抓 push2 clist 成分涨幅榜（域名降级链 push2→push2delay，实时源 IP 限流时切延时源）；腾讯兜底自带代码单只、同花顺兜底无代码单只
- `GET /admin/stock/limit-up/list` 的 `LimitUpStockItem` 新增 `continuation_probability: 0-100` 与 `continuation_factors: [{type, value}]`（读时按封板质量启发式计算不入库，历史日期同样可用；**规则评分非模型预测**）
- 因子 `type` 枚举：`consecutive`（连板高度）/`seal_ratio`（封成比=封单÷成交额）/`break_count`（炸板次数）/`first_seal`（首封时间，原始字符串 `HHMMSS`）/`turnover_rate`（换手率%）；`value` 缺失为 null，前端按 i18n 模板渲染（`page.aStock.limitUp.factor*`）
- 前端：`views/a-stock/industry-board`（领涨股列前三 + flex-height 滚动修复）、`views/a-stock/limit-up`（连板概率列 NTag 高≥65/中40-65/低<40 + NTooltip 因子明细）
- **研报统计（按股票分组）**：`GET /research/reports/stock-stats?days=1..365&stock_code`（研报数/看多评级数(买入/增持/推荐/强烈推荐/优于大市)/机构数/最新研报日期，研报数倒序）；前端研报中心页含快捷时间窗（7天/1月/3月/半年/1年 → days=7/30/90/180/365），表格列可排序，行内「查看研报」联动下方列表筛选

### 板块轮动策略分析（2026-09-01，迁移 0030）

- 前缀 `/admin/stock/rotation`；权限码复用 `stock:board:list`（查询）、`stock:board:sync`（同步/回填）；错误码 11604（成分股同步进行中）/ 11605（历史回填进行中）
- 接口：
  - `GET /rotation/overview?board_type=industry|concept&days=5..60`（默认 10）→ `{snapshot_date, history_days, items: RotationOverviewItem[], themes: RotationThemeItem[]}`（items 按明日评分降序；themes 按热度降序，行业+概念两类板块合并聚合计算）
  - `GET /rotation/switch?board_type&top_n=5..30`（默认 15）→ `{snapshot_date(成分股快照日), items: RotationSwitchItem[]}`（当日涨幅榜前 N 板块）
  - `POST /rotation/sync_stocks?concept_top=5..100`（默认 30）→ `{boards, saved_boards, stocks, failed_boards, snapshot_date}`
  - `POST /rotation/backfill?board_type=industry|concept|all&days=10..250`（默认 all/60）→ `{board_type, days, boards, status: submitted|no_data}`（后台执行立即返回；all=行业+概念合并单任务）
- `RotationOverviewItem` 枚举字段（读时计算不入库，全部因子 None 容错）：`stage: start|ferment|climax|ebb|observe`（启动/发酵/高潮/退潮/蓄势）、`action: attack|ambush|avoid|watch`（主攻/潜伏/回避/观察）、`tomorrow_score: 0-100`；数值字段 `change_pct/gain_3d/gain_5d/gain_10d/rank/rank_pct/rank_change/volume_ratio/inflow_days/limit_up_count/max_consecutive/position_pct` 均可 null，另含 `theme: str|null`（所属主题，THEME_GROUPS 关键词归类；2026-09-02 评分重写：排名阈值统一用 rank_pct 分位数、gathering 主题≥3成员 +10（inflow_ratio≥0.55 再+4）/hot 主题位置≥0.6 成员 -5、资金潜伏型启动=资金连续≥4日+5日涨3-6%+未深跌+非高位、噪音抑制=3日涨幅<1%排名跃升减半与板块指数下跌涨停梯队减半）
- `RotationThemeItem`（2026-09-02 主题聚合）：`{theme, member_count, avg_change_pct, avg_gain_3d, avg_gain_5d, rising_ratio_3d, inflow_ratio, avg_position_pct, limit_up_total, heat: 0-100, status: gathering|active|hot|cooling|flat}`；heat = 40*近3日上涨占比 + 25*min(1,5日均涨幅/5) + 20*资金流入占比 + 15*(1-平均位置)；gathering（集结升温）=低位多板块同涨+资金流入，埋伏首选信号；hot（高位过热）=兑现风险提示；涨停梯队跨类目匹配 = 归一化板块名（去Ⅱ/Ⅲ后缀）∪ 成分股快照 stock_code
- `RotationSwitchItem`：`signal: switching|split|resonance|unknown`（高低切换/分歧/共振/数据不足）、`position_key: gain_10d|gain_5d|change_pct`（分层键按覆盖率降级）、`high_avg_pct/low_avg_pct`、`high_laggards[]/low_starters[]`（高位滞涨/低位启动各 ≤5 只：`{stock_code, stock_name, price, change_pct, amount, position_gain}`）
- 新表 `business_board_stock_daily`（板块成分股日快照，唯一键 record_date+board_type+board_code+stock_code）；`business_board_daily` 通过 push2his 板块日K回填历史缺失日期（on_conflict 只补缺，跳过当日半日 bar，回填行净流入/涨跌家数为 null）
- **board_code 跨源注意**：板块代码跟随当日列表源（东财 BKxxxx / 腾讯兜底 pt0xxxxx），成分股与日K抓取按板块名解析东财代码（归一化+去 Ⅱ 后缀兜底），QQ 独有板块解析失败计 failed_boards
- 定时任务 `stock.rotation_stock_sync`（cron `38 15 * * mon-fri`，板块同步 15:31 之后写当日成分快照）
- analysis 模块新增 `rotation` 类型（仅 close 时段）：`parsed_result` 为 `{rotation_summary, theme_heat[{theme,status,heat,viewpoint}], recent_boards[3-5]{board_name,board_type,stage,change_pct,viewpoint}, tomorrow_boards[3-5]{board_name,board_type,action(主攻/潜伏/回避),confidence(高/中/低),viewpoint}, switch_signals[{board_name,summary}], key_points[], tomorrow_outlook{direction:轮动延续|高低切换|热点退潮|新主线酝酿, summary}}`（theme_heat 2026-09-02 加入：数据注入含主题热度前10，gathering 主题成员优先潜伏、hot 主题中高位规避追涨）；收盘自动生成扩展为 market/sector/rotation；AI 只推演板块层，个股名单由切换表数据侧给出
- 菜单 `ai_rotation-analysis`（ID 8032，sort=10，AI 目录下）；前端 `views/ai/rotation-analysis/index.vue`（左侧行业/概念 RadioGroup + 三页签表格，右侧 `analysis-report-panel.vue` rotation session=close）；回填按钮单次调 `board_type=all`

### 热门个股记录炸板股（2026-09-14，迁移 0032）

- `business_limit_up_stock` 新增 `pool_type: limit_up|broken`（收盘封板 / 涨停后炸板未封住），唯一约束扩为 `(record_date, stock_code, pool_type)`；存量行回填 limit_up
- `GET /admin/stock/limit-up/list` 新增 `pool_type` 筛选参数（默认 all）；`LimitUpStockItem` 新增 `pool_type` 字段；炸板行 `continuation_probability/factors` 为 null（已炸板不算连板概率），`seal_amount/last_limit_up_time/limit_up_reason` 恒为 null（炸板池数据源无此字段），`consecutive_limit_up` 从「涨停统计 days/ct」解析
- `GET /admin/stock/limit-up/stats` 的 `LimitUpStats` 新增 `broken_count`；`total_count`/板块分布/`max_consecutive` 口径不变（仅封板股）
- `POST /admin/stock/limit-up/sync` 返回值加 `broken` 计数；涨停池与炸板池同抓，炸板池失败仅告警不阻塞（akshare `stock_zt_pool_zbgc_em` 限最近 30 交易日）
- 前端 `views/a-stock/limit-up`：池类型 RadioGroup（全部/封板/炸板）+ 状态列（封板红 tag / 已炸板橙 tag）+ 统计卡「炸板家数」

---

## 策略回测模块契约（2026-09-16，迁移 0033）

- 前缀 `/admin/backtest`；权限码复用 `strategy:manage`（未新增菜单/权限种子，菜单项需后台菜单库手工新增指向 `/ai/backtest`）
- 接口：
  - `POST /run`：body `{strategy_id, start_date, end_date, initial_capital=1000000, slippage_pct=0.1, commission_pct=0.025, stamp_tax_pct=0.05}`；异步提交，毫秒级返回 running 状态记录（prompt 型后台回放该策略区间内已记录的真实 AI 信号按 baostock 不复权日线逐日撮合，**非 LLM 逐日重放**；rule 型为逐日因子评估自产信号，见下文「规则型策略契约」）；校验：策略不存在 11501、日期非法/start≥end/区间>3 年 11703、同策略 running 并发 11702
  - `GET /list?strategy_id&status&page&page_size`：统一分页结构，created_at 倒序
  - `GET /{id}`：详情 = 列表项 + `equity_curve`；错误码 11701
  - `GET /{id}/trades?page&page_size`：成交明细统一分页，trade_date+id 升序
  - `DELETE /{id}`：软删，running 状态拒绝（11702）
- `BacktestItem`：`status` 为**字符串三态** `running/success/failed`，无 bool 桥接；`start_date/end_date` 为 `YYYY-MM-DD` 字符串；`result` 可空（running/failed 时为 null）——绩效汇总 `{total_return_pct, annual_return_pct, max_drawdown_pct, sharpe, win_count, loss_count, win_rate, profit_factor, trade_count, final_equity, warnings[]}`，其中 sharpe（样本<2 天）/win_rate（无卖出）/profit_factor（无亏损）可为 null
- `equity_curve`：`[{date, equity, cash, market_value}]`，按交易日升序，前端直接渲染（ECharts 折线）
- `BacktestTradeItem`：`action: buy|sell`；`reason` 买入时为 AI 理由原文、卖出时为枚举 `stop_loss/target_reached/trailing_stop/ai_signal/backtest_end`；`return_rate` 仅 sell 有值（%）；金额/价格/比例均为 `number`（Numeric → float），百分比不带 `%`
- 前端 API：`frontend/src/service/api/backtest.ts`，类型 `Api.Backtest.*`（`frontend/src/typings/api/backtest.d.ts`）；页面 `views/ai/backtest/`（发起表单 + 记录列表 running 时 10s 轮询 + 详情抽屉绩效卡/净值曲线/明细分页）

---

## 因子管理模块契约（2026-09-16，迁移 0034）

- 前缀 `/admin/factor`；权限码复用 `strategy:manage`；错误码新段 11801-11805（11801 不存在 / 11802 公式非法 / 11803 导入失败 / 11804 code 冲突 / 11805 预置不可删）
- 接口（固定路径均声明在 `/{factor_id}` 之前）：
  - `GET /list?category&source&keyword&page&page_size`：统一分页结构，created_at 倒序；keyword 匹配 name/code
  - `POST /`（实际路径 `/admin/factor/`，FastAPI 不允许空前缀+空路径，请求 `/admin/factor` 会 307 重定向）：手工创建，source 固定 custom，code 全局唯一（11804），公式先过白名单校验（11802）
  - `PUT /{factor_id}`：按传入字段更新，code/source 不可改；预置因子可经 `status=false` 停用
  - `DELETE /{factor_id}`：软删；source=preset 拒绝（11805），只能停用
  - `GET /{factor_id}`：详情
  - `POST /import`：body `{url?|content?}` 二选一（400）；JSON 约定 `[{name, code, category?, formula, description?, source_url?}]`（数组或单对象），url 方式 GET 15s 超时；逐条校验公式+code 唯一（含批内重复），非法/冲突跳过 → 返回 `{imported, skipped, errors[]}`；整体获取/解析失败 11803
  - `POST /calc`：body `{factor_id, codes[1..500], end_date?=今天, lookback?=120(5..750)}` → `{factor_id, factor_code, end_date(实际目标交易日), values:[{code, value}], warnings[]}`；历史不足/结果 NaN 的股票跳过进 warnings；北交所等不支持代码跳过
  - `POST /screen`：body `{codes?|strategy_id?(用其股票池), conditions[1..10], end_date?, lookback?=120}`，**不支持全市场选股**（两者必须且只能给一个，400）；条件 AND，`op: gt|gte|lt|lte|top_n`（top_n=按因子值降序前 N，value 须正整数）→ `{total, end_date, matched:[{code, name, factor_values:{因子code: value|null}}], warnings[]}`；name 为 best-effort（该代码最近一条 AI 信号的 stock_name，无则空串）
  - `POST /screen/save-pool`：body `{strategy_id, codes[]}` 覆盖 `strategy.stock_pool={"codes":[...]}`（去重去空白，≤500）；策略不存在 11501 → `{strategy_id, total}`
- `FactorItem.status` 为 **bool**，前端按 `"1"/"2"` 字符串桥接；`source: preset|imported|custom`；`category` 自由字符串（price/momentum/volume/volatility/custom/imported）
- 公式 DSL（`modules/factor/services/formula.py`，ast 白名单严禁 eval/exec）：字段 `open/high/low/close/volume/amount/preclose/pct_chg/vwap`；TS 函数 `REF/MA/SUM/MAX/MIN/STD(ddof=1)/DELTA/COUNT`(2参） `CORR`(3参），窗口须正整数常量；标量 `ABS/LOG/SQRT/SIGN/IF`；截面 `RANK`（仅顶层或算术/比较内，universe 内归一化 pos/total ∈(0,1]，值大→近1，NaN 不参与）；禁止属性/下标/链式比较/BoolOp/IfExp/关键字参数
- 预置因子 17 条（迁移种子，固定 ID 段 2942406616009201-217，按 code 幂等）：bias5/10/20、roc5/10/20、vr1、vr5、vol20、amp20、rsi14、alpha101_006/012/101（source_url=arxiv 1601.00991）、vol_price_corr20、vwap_dev、high20_dev
- 行情复用 backtest 模块 `fetch_market_data`（baostock 不复权日线，`_BAR_FIELDS` 已扩 volume/amount）；目标日=≤end_date 的最后一个交易日，每股截取末 lookback 条
- 前端：`views/ai/factor/`（路由 `ai_factor` /ai/factor，菜单需后台手工新增）三 Tab——因子库（分类/来源/关键字筛选 + 状态开关 + 新建/编辑抽屉（编辑时 code 禁用）+ 导入弹窗（URL/粘贴 JSON 二选一，展示 imported/skipped/errors 明细）；创建走 `/admin/factor/` 尾斜杠）、因子试算（因子+代码/策略带入+目标日+lookback → /calc 结果表 4 位小数 + warnings NAlert）、选股器（手动 codes/策略池二选一 + 动态条件行 AND（>/≥/</≤/前N名）→ /screen 动态因子列结果表 + 存为策略股票池弹窗）；api `service/api/factor.ts` + typings `Api.Factor`；i18n `page.aiFactor.*`

---

## 策略模板市场契约（2026-09-16，迁移 0035）

- 接口挂在 strategy 模块既有子前缀下：`/admin/strategy/strategies/*`；权限复用 `strategy:manage`；新错误码 11509 STRATEGY_IMPORT_INVALID（strategy 段 11501-11509 已补入 i18n 双 yaml 与 error_codes.md）
- `business_ai_strategy` 新增列：`is_template`（Boolean 默认 False，索引）、`source_id`（BigInteger 可空，索引，克隆/导入来源）、`tags`（JSON 可空，字符串列表）
- 接口：
  - `POST /strategies/{id}/clone` → `StrategyItem`：配置/prompt/股票池/时段/风控/tags 原样复制；name=原名（副本）（重名追加（副本2）…）；`is_preset/is_template=False`、`source_id`=原 id、**status=False（克隆件默认停用，实盘引擎只跑启用策略，须手动启用）**
  - `POST /strategies/{id}/publish` / `POST /strategies/{id}/unpublish`：body 可选 `{tags?: string[]}`（传入即覆盖，空数组清空）；翻转 is_template；is_preset 策略允许发布
  - `GET /strategies/templates?page&page_size` → 统一分页 `TemplateItem[]`：`is_template OR is_preset`，created_at 倒序
  - `GET /strategies/{id}/export` → `StrategyExportData`
  - `POST /strategies/import`：body=导出 JSON + `schema_version`（**仅接受 1**，否则 11509）；分类/时段/股票池结构 `{codes: string[]}` 逐项校验（11509），百分比越界走 pydantic 400（同创建接口）；name 冲突自动追加（2）（3）…；新件 is_preset/is_template=False、status=False
- `StrategyItem` 新增字段：`is_template: bool`、`source_id: number|null`、`tags: string[]|null`（`status` 仍为 bool 直传）
- `TemplateItem = StrategyItem + clone_count`（存活克隆件计数，软删不计）`+ last_backtest: {start_date, end_date, total_return_pct, max_drawdown_pct, win_rate, trade_count} | null`（该 strategy_id 最新一条 status=success 回测的 result 摘要，无则 null）
- 导出 JSON（schema_version=1）：`{schema_version, name, description, category, prompt_template, stock_pool, execute_periods, max_positions, stop_loss_pct, take_profit_pct, trailing_drawdown_pct, tags, strategy_type?, rule_config?}`——不含 id/状态/时间戳；导入策略 `source_id` 恒为 None（跨环境迁移原 id 无意义）；**2026-09-16 P2 起新增 `strategy_type`/`rule_config` 两可选字段**（旧格式 JSON 缺省按 prompt 型导入，schema_version 保持 1 向后兼容；rule 字段校验失败统一归 11509）
- 前端：`views/ai/analysis/` 策略管理 Tab 操作列加 克隆(Popconfirm)/导出(Blob 下载 `<名>.strategy.json`)/发布(NDynamicTags 弹窗)/取消发布，名称列加「模板」tag；第四 Tab「策略模板」= `modules/strategy-template.vue`（模板表格：tags/克隆次数/last_backtest 绩效红涨绿跌 + 克隆此模板 + 导入弹窗）；i18n 键在 `page.aiStrategy.*`（与既有三 Tab 同域，非 aiAnalysis）

---

## 规则型策略契约（2026-09-16，迁移 0036）

- `business_ai_strategy` 新增列：`strategy_type`（String(20) NOT NULL 默认 `prompt`，索引 `ix_ai_strategy_strategy_type`；存量回填 prompt）与 `rule_config`（JSON 可空）——`rule_config = {"buy_conditions": [{factor_id, op, value}], "sell_conditions": [...]}`，`op ∈ gt/gte/lt/lte`（**无 top_n**：规则信号是逐股布尔判定，非截面排名选股）；prompt 型 rule_config 必须为 null
- 创建/更新接口加两字段；校验：rule 型 buy_conditions 非空（schema min_length=1）、sell_conditions 可空（空=仅靠止损/止盈/回撤机械离场）、factor_id 全部存在且启用、股票池必须非空（规则型不支持全市场选股）；新错误码 **11510 STRATEGY_RULE_CONFIG_INVALID** / **11511 STRATEGY_RULE_NO_POOL**；**strategy_type 创建后不可改——更新接口静默忽略请求值，按存量类型校验 rule_config**
- 执行分流：`POST /strategies/{id}/run` 与调度任务 `strategy.run_execute` 按 strategy_type 分流——rule 型走 `RuleExecutor`（复用 StrategyExecutor submit_run 异步模式：并发守卫 11508/同日同时段去重口径一致，**无 LLM 调用**，universe=股票池∪当前持仓，因子取最近交易日 lookback=120），Run 的 `ai_raw_response` 为规则评估摘要文本（基准日/条件/信号计数/告警）；买入信号 `ref_buy_price`=基准日收盘价、止损/目标价按策略 pct 折算；信号口径与 prompt 型一致（落 business_strategy_signal 由每分钟交易引擎执行）
- 回测分流：`POST /admin/backtest/run` 按 strategy_type 分流——prompt=`recorded_replay`（回放区间内已记录真实信号，口径不变），rule=`rule_daily_eval`（逐交易日 D 用截至 D-1 数据评估自产信号、D 日开盘成交，**严格无未来函数**；每票 bars 一次载入、因子经 `formula.py calc_factor_series` 全历史序列一次算好，RANK 按交易日逐日跨 universe 截面）；两模式均在 `result.warnings` 首条标注；BacktestItem 契约不变；rule 型 submit 即校验空池/无买入条件（11511/11510）
- 前端：策略抽屉顶部「策略类型」单选（编辑时禁用）、rule 型隐藏提示词改显买入/卖出两组条件构建器（共享组件 `src/components/common/factor-condition-builder.vue`，选股器同用——选股器传 allow-top-n，策略规则不传）、股票池 rule 型必填提示、列表名称列「规则」tag；回测页策略下拉标注 [AI]/[规则] + 模式说明文案；typings `Api.Strategy.{StrategyType,RuleOp,RuleCondition,RuleConfig}`

---

## 绩效深化（P3，2026-09-16，迁移 0037）

- `business_strategy_position` 加 `run_id`（BigInteger 可空，索引 `ix_strategy_position_run`）——建仓来源执行记录 ID，交易引擎建仓时写入 `sig.run_id`；存量为 NULL 不回填（归因归 unknown 组）
- `business_backtest` 加 `slippage_model`（String(20) NOT NULL 默认 `'fixed'`，server_default 回填后去除，仿 0035/0036）
- `GET /admin/strategy/positions/stats` 每项新增 `compound_return_rate: number|null`——**复利口径**（closed 持仓按 sell_time 升序逐笔 `(1+r/100)` 连乘 -1，%），与既有 `total_return_rate`（加总口径=逐笔简单求和）并存；无平仓为 null
- 新端点（挂在 `stats_router`，权限复用 `strategy:position:list`，`strategy_id` 必填，策略不存在 11501）：
  - `GET /admin/strategy/stats/equity-curve?strategy_id` → `[{date, equity, holding_count}]`：等权平均净值（基准 100），按持仓跟踪日志逐日取每股末条、持有期内前向填充；**建仓日记 0、卖出日锁定最终 return_rate 终止**；只输出有 track log 的日期（非交易日历）
  - `GET /admin/strategy/stats/attribution?strategy_id` → `{by_sell_reason: [{reason, count, win_rate, avg_return, total_return}], by_run_period: [{period, ...同上}]}`；by_sell_reason 仅 closed 持仓；**by_run_period 含 holding 浮盈**（period=建仓 run 的 execute_period），存量 run_id=NULL 归 `unknown` 组
- 回测滑点模型：`POST /admin/backtest/run` body 加 `slippage_model: fixed|amp`（默认 fixed）；fixed=slippage_pct 直接为滑点%（上限 10）；amp=振幅比例，**实际滑点=当日振幅(high-low)/preclose×slippage_pct/100**（缺 preclose/高低价回退 fixed 口径），slippage_pct 作系数上限 50；越界均报 11703（无新错误码）；`BacktestItem` 带 `slippage_model`
- 回测僵死恢复：TradeEngine `execute_tick` 维护段新增——`status=running` 且 `coalesce(started_at, created_at) < now-20min`（`BACKTEST_STALE_MINUTES=20`）的回测置 `failed`，error_msg=「执行超时（超过 20 分钟未完成，疑似进程重启）」，计数 `expired_stale_backtests`；与存量 run/信号超时清理同段同 commit
- 前端：回报率统计 Tab 加「复利收益率」列（IconTooltip 说明两口径差异）+ 策略选择器联动净值曲线图与归因双卡（按卖出原因/按执行时段，红涨绿跌，unknown=历史未知）；回测发起表单高级参数加滑点模型单选（amp 时 label/上限/提示切换）；详情抽屉头部加滑点模型 tag；**`equity-chart.vue` 从 `views/ai/backtest/modules/` 提升为公共组件 `src/components/common/equity-chart.vue`**（holding_count 走副轴半透明柱，回测/模拟盘两处共用，auto-import 生效）

---

## 参数寻优 sweep 契约（2026-09-16）

- `POST /admin/backtest/sweep`：**同步接口**，结果**不落** business_backtest 表；权限复用 `strategy:manage`；无新错误码（策略不存在 11501，参数类一律 11703）
- 请求：`{strategy_id, start_date, end_date, initial_capital?=1000000, slippage_model?="fixed", slippage_pct?, commission_pct?, stamp_tax_pct?, grid: {stop_loss_pct?[], take_profit_pct?[], trailing_drawdown_pct?[]}, buy_condition_scan?: {condition_index, values[]}}`；日期/滑点校验口径同 `/run`
- 校验：grid 三参数至少一个非空或存在 buy_condition_scan（全空 11703）；**笛卡尔积 ≤27**（超出 11703，消息含实际组合数）；prompt 型不允许 buy_condition_scan（11703）；rule 型 condition_index 必须指向 `rule_config.buy_conditions` 既有行（11703）
- 实现：行情/信号/因子序列只准备一次（复用 backtest_runner `_recorded_signals` / `_rule_prepare` 路径，后者为 sweep 重构拆出）；逐组调 engine `run_replay` 纯函数回放——引擎状态全局部，唯一外部可变共享 warnings 列表每组传副本隔离；rule 扫描组用条件 value 覆盖后的 buy_conds 重新 `gen_rule_signals`
- 响应：`{strategy_id, strategy_name, mode(recorded_replay|rule_daily_eval), total_runs, results: [{params: {stop_loss_pct, take_profit_pct, trailing_drawdown_pct, buy_condition?: {index, factor_id, value}}, total_return_pct, annual_return_pct, max_drawdown_pct, sharpe, win_rate, profit_factor, trade_count, final_equity, is_baseline}]}`——**按 total_return_pct 降序**；策略当前参数所在组合标 `is_baseline=true`，**当前参数不在网格中时自动追加一组 baseline**
- 已知现象（非 bug）：prompt 型网格可能出现相邻参数组绩效并列——AI 信号自带 stop_loss_price/target_sell_price 时，策略止损/止盈参数仅在信号价格位无效（方向错误/缺失）时兜底，未触发的参数组结果自然一致
- 前端：回测页「参数寻优」弹窗 `views/ai/backtest/modules/sweep-modal.vue`（自载策略/因子列表）——网格候选值逗号分隔实时算组合数（>27 红字禁提交）、rule 型显买入条件扫描区、结果表最优行高亮 + baseline 行「当前参数」tag、「应用该组参数」Popconfirm 后经 `PUT /admin/strategy/strategies/{id}` 整体写回（rule 含条件行 value，baseline 行禁用）；api `fetchRunBacktestSweep`，typings `Api.Backtest.{BacktestSweepParams,SweepResultItem,BacktestSweepResult,...}`，i18n `page.aiBacktest.sweep.*`
- 调优数据基线见记忆 `business/2026-09-16_strategy_backtest_baseline.md`（10 策略绩效矩阵，回测记录保留在库）
