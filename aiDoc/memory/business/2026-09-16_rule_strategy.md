# 规则型策略（P2 收尾：因子条件固化为策略并接入回测）

## 需求描述

路线图 P2 收尾：把因子条件固化为策略（strategy_type=rule + rule_config 买卖条件），规则评估产信号进现有交易引擎，并接入回测——打通 因子 → 规则策略 → 回测 → 模拟盘 闭环；前端策略抽屉加规则模式、回测页按类型适配。

## 状态

已完成（后端 + 前端 + 导出/导入补丁）

## 涉及范围

### 后端

- `business_ai_strategy` 加 2 列（迁移 0036）：`strategy_type`（String(20) NOT NULL 默认 'prompt'，索引，server_default 回填后去除，仿 0035）、`rule_config`（JSON 可空，`{"buy_conditions": [{factor_id, op, value}], "sell_conditions": [...]}`，op ∈ gt/gte/lt/lte 无 top_n）
- `StrategyService._validate_rule_config`：rule 型 buy_conditions 非空、股票池非空（11511）、因子全部存在且启用、prompt 型 rule_config 必须 null（11510）；**strategy_type 创建后不可改=更新时静默忽略**；clone 复制两字段；export/import 携带两字段（schema_version 仍 1，旧格式缺省 prompt，导入校验失败统一归 11509）
- 新 `modules/strategy/services/rule_executor.py`：`RuleExecutor` 复用 StrategyExecutor submit_run 异步模式（并发守卫/同日同时段去重口径一致，无 LLM 调用）；universe=股票池∪当前持仓，因子取最近交易日 lookback=120（复用 factor_calc `_fetch_universe_bars` + formula `calc_factor_values`）；买入信号 ref_buy_price=基准日收盘价、止损/目标按策略 pct 折算；Run.ai_raw_response=规则评估摘要；`gen_rule_signals()` 纯函数供回测共用
- 调度 `strategy.run_execute` 与手动 run 端点按 strategy_type 分流
- 回测：`backtest_runner._run` 分流 `_recorded_signals`（原逻辑）/`_rule_signals`（逐交易日 D 用 ≤D-1 数据评估产信号，run_date=D-1 次日开盘成交，走 run_replay 先卖后买/T+1/止损止盈回撤/费用/期末强平不变）；`formula.py` 新增 `calc_factor_series`（全历史序列，RANK 按交易日逐日跨 universe 截面，无前视）；两模式 warnings 首条标注 recorded_replay/rule_daily_eval；submit 对 rule 型空池/无条件快速失败
- 错误码 11510/11511 + i18n 双 yaml + error_codes.md

### 前端

- 共享条件构建器 `src/components/common/factor-condition-builder.vue`（allowTopN/allowEmpty/max props + extra 插槽；自行加载启用因子下拉）；`factor-screen.vue` 改为复用（传 allow-top-n）
- 策略抽屉：顶部「策略类型」单选（编辑禁用）、rule 型隐藏提示词显示买入（必填）/卖出（可空）条件构建器、股票池 rule 必填提示、提交组 rule_config（prompt 型 null）；列表名称列「规则」tag
- 回测页：策略下拉标注 [AI]/[规则] + 模式说明文案
- typings `Api.Strategy.{StrategyType,RuleOp,RuleCondition,RuleConfig}` 与请求响应字段；i18n `page.aiStrategy.*`/`page.aiBacktest.*` 双语 + app.d.ts

## 约束与备注

- 验证证据：rule 回测近 3 月（600519/601318，bias20<-5 买 / >5 卖）total_return=+2.11%、maxDD=2.10%、sharpe=1.65、6 笔成交；**无前视抽查**：601318 成交日 2026-06-22 的信号理由含 bias20=-7.379793（基准日 2026-06-18<成交日），用 ≤基准日 数据独立重算=-7.379793 一致；prompt 型回测回归 success；校验负例 4 项（11510×2/11511/top_n 被 schema 拒）；`pnpm typecheck` 24 错=基线、`pnpm build:test` 通过；冒烟数据全部硬删清理
- 坑与偏离：①strategy_type 不可改采**忽略**口径（非拒绝）；②导出/导入 schema_version 仍 1（新增可选字段向后兼容）；③共享组件落 `src/components/common/`（框架 auto-import 约定目录）而非 view modules/；④条件行 op 类型复用 `Api.Factor.ScreenOp`，提交时收窄断言为 RuleOp；⑤后端 import 的 rule 校验错误统一包装 11509（延续该端点契约），11510/11511 只在创建/更新出现；⑥卖出条件为空=仅机械离场，不产规则卖出信号
- 沿用坑：MappedAsDataclass 列顺序（两列带默认值追加尾部）、service 自 commit 冒烟数据须硬删、规则型不支持全市场选股（与选股器同口径）

## 相关文件

- 后端：`backend/database/models/business/strategy.py`、`backend/modules/strategy/services/{rule_executor.py,strategy_service.py}`、`backend/modules/strategy/schemas/strategy.py`、`backend/modules/strategy/endpoints/strategy.py`、`backend/modules/scheduler/tasks/strategy_run.py`、`backend/modules/factor/services/formula.py`、`backend/modules/backtest/services/{backtest_runner.py,backtest_service.py}`、`backend/alembic/versions/0036_add_rule_strategy.py`、`backend/core/response/response_code.py`、`backend/core/i18n/locales/{zh-CN,en-US}.yaml`、`error_codes.md`
- 前端：`frontend/src/components/common/factor-condition-builder.vue`、`frontend/src/views/ai/factor/modules/factor-screen.vue`、`frontend/src/views/ai/analysis/{index.vue,modules/strategy-operate-drawer.vue}`、`frontend/src/views/ai/backtest/index.vue`、`frontend/src/typings/api/strategy.d.ts`、`frontend/src/locales/langs/{zh-cn,en-us}.ts`、`frontend/src/typings/app.d.ts`
- 契约：`aiDoc/contracts/boundary.md`「规则型策略契约（2026-09-16，迁移 0036）」

## 记录日期

2026-09-16
