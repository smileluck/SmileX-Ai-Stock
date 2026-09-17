# 参数寻优 sweep（P3 收尾：风控网格 + 条件阈值扫描 + 一键应用）

## 需求描述

Part A 基线报告给出调参方向后，需要数据支撑的调参工具：对策略风控三参数（止损/止盈/回撤止盈）做网格寻优，rule 型策略另支持单条买入条件阈值扫描；结果对比表可直接「应用该组参数」写回策略配置。同步接口、不落库、组合上限 27。

## 状态

已完成（后端 + 前端）

## 涉及范围

### 后端

- 新 `modules/backtest/services/sweep_service.py` `SweepService.run_sweep`：校验（策略 11501；日期同 /run；grid 全空且无 scan 11703；笛卡尔积 >27 报 11703 含实际组合数；prompt+scan 11703；rule condition_index 越界 11703）→ 数据准备一次 → 逐组 `run_replay` 纯函数回放 → 按 total_return_pct 降序，当前参数组标 is_baseline（不在网格则追加）
- `backtest_runner` 重构复用：`_recorded_signals` 改签名为 start/end 日期参数；`_rule_signals` 拆出 `_rule_prepare`（行情 bars/交易日/因子全序列/条件快照上下文），信号生成下沉调用点——sweep 扫描组覆盖条件 value 后重新 `gen_rule_signals`
- 端点 `POST /admin/backtest/sweep` 注册在 `/{backtest_id}` 之前；schemas 新增 `SweepGrid/BuyConditionScan/BacktestSweepRequest/SweepParams/SweepResultItem/BacktestSweepResult`，常量 `MAX_SWEEP_COMBINATIONS=27`

### 前端

- 新 `views/ai/backtest/modules/sweep-modal.vue`：自载策略（全量含 rule_config）与因子列表；网格候选值逗号分隔、实时笛卡尔积（0 组灰字提示 / >27 红字禁提交）；rule 型显买入条件扫描区（条件下拉显示因子名+op+当前值，填候选值即启用）；结果表最优行（首行）绿色高亮+「最优」tag、baseline 行「当前参数」tag；「应用该组参数」Popconfirm → 整体组装 StrategySaveParams 写回（rule 含条件行 value 覆盖，其余行保留），baseline 行禁用；成功 emit applied 父级刷新策略下拉
- api `fetchRunBacktestSweep`；typings `Api.Backtest.{SweepGrid,BuyConditionScan,BacktestSweepParams,SweepParams,SweepResultItem,BacktestSweepResult}`；i18n `page.aiBacktest.sweep.*` 21 键双语 + app.d.ts

## 约束与备注

- 验证证据：①rule 冒烟策略 2×2 网格（stop [2,4]×take [5,8]，当前 3/4/5 不在网格）→ total_runs=5，4 组互异 **+2.4969/+2.1053/+2.0785/+1.6833 vs baseline +1.4142**，且 baseline 与同窗口单独 /run 逐位一致（含笔数）；②prompt 核心资产（158 信号）stop [3,5]×take [6,10] → 5 组，baseline(8,20,5)=**-4.1844% 与 Part A 基线 id=3531772914835456 逐位一致**；③负例 4 项全 11703（28 组含组合数/prompt+scan/condition_index=9 越界/全空 grid）；④sweep 前后 business_backtest 恒为对照组 1 条（不落库验证）；⑤`pnpm typecheck` 新改动 0 错误、`pnpm build:test` 通过；冒烟数据已硬删
- 坑与偏离：①引擎纯函数可重入的唯一缺口是 `warnings` 列表会被 append——每组传 `list(base_warnings)` 副本隔离；②prompt 型相邻参数组绩效并列非 bug（AI 信号自带价格位时参数仅兜底）；③buy_condition_scan 的 rule 正例未进 smoke（规格只要网格+负例），逻辑走 gen_rule_signals 条件覆盖；④baseline 行禁应用为防御性处理（参数与当前一致）；⑤前端弹窗自载数据（沿用 factor-condition-builder 模式）而非父级传入
- 调优基线数据见 `2026-09-16_strategy_backtest_baseline.md`

## 相关文件

- 后端：`backend/modules/backtest/services/sweep_service.py`、`backend/modules/backtest/services/backtest_runner.py`、`backend/modules/backtest/schemas/backtest.py`、`backend/modules/backtest/endpoints/backtest.py`
- 前端：`frontend/src/views/ai/backtest/modules/sweep-modal.vue`、`frontend/src/views/ai/backtest/index.vue`、`frontend/src/service/api/backtest.ts`、`frontend/src/typings/api/backtest.d.ts`、`frontend/src/locales/langs/{zh-cn,en-us}.ts`、`frontend/src/typings/app.d.ts`
- 契约：`aiDoc/contracts/boundary.md`「参数寻优 sweep 契约（2026-09-16）」

## 记录日期

2026-09-16
