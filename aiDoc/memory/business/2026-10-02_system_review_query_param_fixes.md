# 系统功能审阅与修复（AI 分析持仓空列表 + 同族缺陷全量清理）

## 需求描述

用户报告「AI 分析持仓目前返回为空」，随后要求审阅并优化系统中的功能、确保功能正确运行，并给出优化建议修复清单。本次为缺陷修复型任务：从单点 bug 入手，扩展为对查询参数链路、错误路径、dev 运行环境三类同族缺陷的全量扫描、修复与回归验证。

## 状态

已完成（修复已验证，backend dev server 需手动重启一次以激活热重载修复，见「约束与备注」）

## 根因与修复明细

### 1. AI 分析持仓空列表（原始 bug，已修复）

- **现象**：持仓 tab 全空，且每 60s 轮询持续失败，页面无任何报错。
- **根因链**（三层叠加）：
  1. naive-ui NSelect（clearable）清空后 v-model 值为 `null`；
  2. 前端 axios 用 `qs.stringify` 默认参数序列化 query，**null 被序列化成 `key=` 空串**（不是丢弃，只有 undefined 被丢弃）；
  3. 后端 `strategy_id: Optional[int] = Query(None)` 对空串返回 422「请输入有效的整数」，前端 `if (!error)` 静默吞掉 → 列表保持空。
- **触发证据**（app.log 2026-10-01）：23:18:33 带 strategy_id=3615546917396480 正常 200；23:18:43 用户清空筛选后全部 `strategy_id=""` → 422 ×28 次。
- **修复**：
  - `backend/modules/strategy/endpoints/position.py`（列表 + stats 两处）、`backend/modules/backtest/endpoints/backtest.py`（回测列表）：改为 `Annotated[Optional[int], Query(description=...), BeforeValidator(parse_optional_int)] = None`；
  - `backend/modules/strategy/endpoints/strategy.py`：status 改 `Annotated[Optional[bool], Query(...), BeforeValidator(parse_bool)] = None`；`position.py` sort_desc 同法（服务层签名同步放宽 `Optional[bool]`）；
  - `frontend/src/views/ai/analysis/index.vue`：`strategy_id: positionSearch.strategy_id || undefined`；`frontend/src/views/ai/backtest/index.vue`：`??` → `||`；
  - `frontend/packages/axios/src/options.ts`：paramsSerializer 加 `{ skipNulls: true }`（根治发送侧，17 组 useTable searchParams 直传 null 的脏空参一并消除）。
- **⚠️ 关键实现细节（FastAPI 0.127 实测）**：内联 Query 参数上 `Annotated[Optional[int], BeforeValidator(f)] = Query(None)` 的校验器会被**静默剥离**（'' 仍 422）；唯一生效写法是把 `Query()` 放进 Annotated、默认值用 `=` 设置。查询参数模型（BaseModel+Depends）无此问题。验证必须走 TestClient/真实 HTTP。

### 2. uvicorn reload 恶性循环（结论已于次日修正）

- **当时现象**：dev 后端进程频繁重启；trade_engine/新闻抓取等定时任务随机报 `CancelledError`。
- **当时结论（已证伪）**：日志写入触发热重载。**2026-10-02 复核修正**：uvicorn 0.40 的 watchfiles 上报所有变更（debug 行"N changes detected"即原始上报），但 `should_restart()` 的 FileFilter 默认只放行 `*.py`——午夜日志轮转引发 2 次检测、worker 未重启为实证。当天重启实为用户真实编辑 .py 的正常重载（"数据库连接池已关闭" 214 次多为任务子进程退出，非服务器重启数）。`reload_includes=["*.py"]` 保留（与默认等价、显式化无害），无需手动重启。
- **真正遗留**：reload 父进程与 worker 双进程各持日志轮转 handler 的午夜竞态（见 2026-10-02 第二轮审阅记录）。

### 3. 错误路径二次 500（2 处，已修复）

`ResponseModel[X]` 泛型路由的错误分支直接构造 `ResponseModel(code=500, data=None)` 会撞 data 必填校验触发 ResponseValidationError，真实错误被吞：
- `backend/modules/app/endpoints/auth.py` PUT /users/me：移除吞异常的 try/except（交给全局 handler）；
- `backend/modules/admin/endpoints/sys/notice.py` publish：改 `raise HTTPException(500, detail=t(...))`。

### 4. 扫描无命中的家族（记录备查）

- `CustomError(err_code=...)` 参数误用：全库 110 处调用 0 命中；
- `response_base.fail()` + 泛型 response_model：活跃代码 0 命中（仅注释块 1 处）；
- 其余模块的 str 型筛选参数均有 truthy `if x:` 或 BeforeValidator 兜底。

## 验证结论

- API 回归 10/10 通过（空串→200、非法 int 仍 422、bool 桥接 "1"/"2" 正常、正常过滤不受影响）；
- 前端 typecheck：改动文件 0 错误（全库 10 个既有错误均低于基线 39 且与本次无关）；
- 浏览器端到端（端口 9527）：登录 → /ai/analysis?tab=positions&strategy_id=3615546917396480（预填）→ 通过 Vue onUpdate:value 处理器数组模拟清空筛选 → 表格立即恢复 20 行持仓（建设银行/中国电信/山西汾酒等）；
- 用户原会话的页面轮询在修复后已恢复 200（backend log 实证）。

## 遗留优化建议（未实施，按优先级）

1. ~~手动重启 backend dev server~~（2026-10-02 修正：reload 根因结论有误，无需为 reload_includes 重启）。
2. 信号生成侧注入实时行情、ref 价偏差 >3% 拒单/重算（既有结论：67 笔已执行买入信号 ref_buy_price 平均偏差 29.3%，期望为负的根因）。
3. 前端统一 `??` → `||`（factor-library/financial-analysis/research-report 共 5 处字符串筛选；axios skipNulls 后属纵深防御，非必须）。
4. useTable searchParams 增加集中式 null/'' → undefined 净化（skipNulls 已挡 null，防未来 '' 源）。
5. backtest.py 裸 int 的 page/page_size、position.py 的 limit 与必填 strategy_id 保持现状（前端恒传数字，无现实触发路径），新增筛选参数时按 Annotated 写法走。

## 约束与备注

- 本次未动数据库结构，无迁移。
- 排查过程中确认 5173 端口跑的是另一项目（SmileX-Admin-Gin/web），本项目前端 dev 端口为 **9527**。
- .env 的 DATABASE__URL 用户名 posgres 有误（实际 postgres），本次未改（避免影响用户启动脚本），已在会话记忆中记录。

## 相关文件

- backend/main.py、backend/modules/strategy/endpoints/{position,strategy}.py、backend/modules/backtest/endpoints/backtest.py、backend/modules/app/endpoints/auth.py、backend/modules/admin/endpoints/sys/notice.py、backend/modules/strategy/services/position_service.py
- frontend/packages/axios/src/options.ts、frontend/src/views/ai/analysis/index.vue、frontend/src/views/ai/backtest/index.vue

## 记录日期

2026-10-02
