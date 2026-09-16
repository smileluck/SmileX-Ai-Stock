# 策略模板市场（模板化/克隆/导入导出）

## 需求描述

路线图 P1：策略（提示词+股票池+时段，已 JSON 化）增加模板市场能力，对标 BigQuant 社区「一键克隆、改参数重跑」的低成本形式——克隆、发布/下架模板、模板市场列表（附克隆次数与最近回测绩效）、策略 JSON 导出/导入（跨环境迁移）。

## 状态

已完成（后端 + 前端）

## 涉及范围

### 后端

- `business_ai_strategy` 加 3 列（迁移 0035）：`is_template`（Boolean 默认 False，索引；NOT NULL 先 server_default=false 回填后去除）、`source_id`（BigInteger 可空，克隆/导入来源）、`tags`（JSON 可空字符串列表）
- `modules/strategy/services/strategy_service.py`：`clone`（配置原样复制、name=原名（副本）重名追加序号、**默认停用**、is_preset/is_template=False、source_id=原 id）、`set_template`（publish/unpublish 翻转 is_template，body tags 覆盖更新）、`list_templates`（is_template OR is_preset，附 clone_count 存活计数 + last_backtest 最近 success 回测摘要）、`export_strategy`/`import_strategy`（schema_version 仅接受 1，name 冲突追加（2）（3）…，新件默认停用）
- 6 端点挂既有 `/admin/strategy/strategies` 子前缀；固定路径 /templates、/import 声明在 /{strategy_id} 之前
- 错误码：新增 11509 STRATEGY_IMPORT_INVALID；strategy 段 11501-11509 整体补入 i18n 双 yaml（此前从未入 yaml）与 error_codes.md（原 8/9 节顺延 9/10）

### 前端

- `views/ai/analysis/` 策略管理 Tab：操作列加 克隆(Popconfirm)/导出(Blob 下载 `<名>.strategy.json`)/发布(NDynamicTags 弹窗)/取消发布，名称列加「模板」tag
- 第四 Tab「策略模板」= `modules/strategy-template.vue`：模板表格（tags/克隆次数/last_backtest 绩效红涨绿跌/克隆此模板）+ 导入弹窗（粘贴 JSON，前端 JSON.parse 预检）
- `service/api/strategy.ts` +6 函数；typings `Api.Strategy` 加 TemplateItem/StrategyExportData/StrategyImportParams 等；i18n `page.aiStrategy.*` +31 键双语 + app.d.ts 同步

## 约束与备注

- 克隆/导入件**默认停用**是核心语义：实盘引擎只跑启用策略，防止无意开跑
- 接口实际路径带 `/strategies` 子前缀（如 `/admin/strategy/strategies/{id}/clone`），非需求字面 `/admin/strategy/{id}/*`——与既有 CRUD 同资源同前缀
- i18n 键落 `page.aiStrategy.*`（该页既有三 Tab 全在此命名空间；`aiAnalysis` 是报告面板另一套），未按需求字面放 aiAnalysis
- 克隆次数只统计存活（未软删）克隆件；导入件 source_id 恒 None（导出 JSON 不含来源 id，跨环境无意义）
- StrategyCreateRequest/更新接口未加 tags 入参（tags 经 publish/import 写入）
- 坑沿用：Base 是 MappedAsDataclass，无默认值列必须排在有默认值列之前（本次 3 列全带默认值，追加在尾部即可）；策略各 service 方法内部自 commit，smoke 冒烟数据须硬删清理
- typecheck 存量基线 24 错（trailingDrawdown/aiAnalysis 缺键等），本次改动 0 新增

## 相关文件

- 后端：`backend/database/models/business/strategy.py`、`backend/modules/strategy/{schemas,endpoints,services}/strategy.py`、`backend/alembic/versions/0035_add_strategy_template_fields.py`、`backend/core/response/response_code.py`、`backend/core/i18n/locales/{zh-CN,en-US}.yaml`、`error_codes.md`
- 前端：`frontend/src/views/ai/analysis/index.vue`、`frontend/src/views/ai/analysis/modules/strategy-template.vue`、`frontend/src/service/api/strategy.ts`、`frontend/src/typings/api/strategy.d.ts`、`frontend/src/locales/langs/{zh-cn,en-us}.ts`、`frontend/src/typings/app.d.ts`
- 契约：`aiDoc/contracts/boundary.md`「策略模板市场契约（2026-09-16，迁移 0035）」

## 记录日期

2026-09-16
