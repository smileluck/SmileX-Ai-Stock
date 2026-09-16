# 绩效深化（P3：复利口径 + 净值曲线 + 归因 + 滑点模型 + 僵死恢复）

## 需求描述

P3 绩效深化四块：①迁移 0037（position.run_id 建仓归因 + backtest.slippage_model）；②模拟盘绩效深化——stats 加复利收益率、新增净值曲线与归因两接口；③回测滑点模型 fixed/amp（振幅比例）；④回测僵死恢复（进程重启后 running 残留回收进 TradeEngine tick 维护段）；前端同步（统计 Tab 增强 + 回测表单滑点模型）。

## 状态

已完成（后端 + 前端）

## 涉及范围

### 后端

- 迁移 0037：`business_strategy_position.run_id`（可空+索引，存量 NULL 不回填）、`business_backtest.slippage_model`（NOT NULL 默认 'fixed'，server_default 回填后去除，仿 0035/0036）
- 交易引擎建仓写 `run_id=sig.run_id`；`BACKTEST_STALE_MINUTES=20`，execute_tick 维护段把 running 且 `coalesce(started_at,created_at)` 超 20 分钟的回测置 failed（「疑似进程重启」），计数 `expired_stale_backtests`
- `PositionService`：get_stats 加 `compound_return_rate`（closed 按 sell_time 升序复利连乘）；新增 `get_equity_curve`（等权平均净值基准 100，track log 按股按日取末条、持有期前向填充、建仓日 0、卖出日锁定，只输出有 track log 日期）与 `get_attribution`（by_sell_reason 仅 closed；by_run_period 含 holding 浮盈，run_id NULL 归 unknown）
- 新端点 `GET /admin/strategy/stats/{equity-curve,attribution}`（stats_router，权限 `strategy:position:list`，strategy_id 必填）
- 回测：`BacktestRunRequest.slippage_model`（fixed 上限 10 / amp 上限 50，越界 11703）；engine `_slippage(bar)`：amp=振幅(high-low)/preclose×系数/100，缺数据回退 fixed；买卖两处成交价接入；submit/runner/BacktestItem 全链路透传

### 前端

- `equity-chart.vue` 提升为公共组件 `src/components/common/equity-chart.vue`（props 泛化 `{date,equity,holding_count?}[]`，holding_count 走副轴半透明柱），回测详情与统计 Tab 共用
- 回报率统计 Tab：复利收益率列（IconTooltip 说明加总 vs 复利口径）+ 策略选择器（默认首个）联动净值曲线 + 归因双卡（卖出原因/执行时段中文化映射，unknown=历史未知）
- 回测发起表单：高级参数加滑点模型单选，amp 时 label 切「滑点系数(%)」+ 提示 + 上限 50（切回 fixed 钳到 10）；详情抽屉头部加滑点模型 tag
- typings `Api.Strategy`（compound/EquityCurvePoint/Attribution*）与 `Api.Backtest.SlippageModel`；i18n `page.aiStrategy.*` 13 键 + `page.aiBacktest.*` 5 键双语 + app.d.ts（顺带补存量缺失的 `aiStrategy.reasonTrailingStop`）

## 约束与备注

- 验证证据：①复利口径 +10%/-5%/+20% 三笔 → compound=25.4 与手工 cumprod 一致（对照加总 25.0）；②净值曲线真实策略 2942406616009107（29737 条 track log）21 点，100.13→97.99 日期升序；③归因 unknown 组存在（存量 run_id NULL）；④滑点对照同策略同区间 fixed(0.1)=2.1107% vs amp(10)=2.122%，6v6 笔成交 3 处同笔价差、slippage_model 落库；⑤僵死恢复 tick 返回 expired_stale_backtests=1，DB 置 failed；⑥`pnpm typecheck` 本次改动 0 错误（基线勿动）、`pnpm build:test` 通过；冒烟数据全部硬删无残留
- 坑：①`business_position_track_log` **无 strategy_id**，须 join position 表关联；②async 会话 `rollback()` 后访问 ORM 过期属性抛 **MissingGreenlet**（脚本须先提取纯值/用原生 SQL 断言）；③同会话 identity map 陈旧读——get_by_id 不覆盖已加载属性，断言须走原生 SQL；④`BusinessBacktest` 为 MappedAsDataclass，构造不接受 `created_at`（有默认值列须后置赋值或 SQL 回填）
- 口径偏离（设计注明）：by_run_period 含 holding 浮盈；unknown 组含存量 run_id=NULL 持仓；equity-curve 只输出有跟踪数据日期；无新错误码（复用 11703）

## 相关文件

- 后端：`backend/alembic/versions/0037_position_run_id_backtest_slippage_model.py`、`backend/database/models/business/{strategy.py,backtest.py}`、`backend/modules/strategy/services/{trade_engine.py,position_service.py}`、`backend/modules/strategy/schemas/strategy.py`、`backend/modules/strategy/endpoints/{position.py,__init__.py}`、`backend/modules/strategy/router.py`、`backend/modules/backtest/{schemas/backtest.py,services/backtest_service.py,services/backtest_runner.py,services/engine.py}`
- 前端：`frontend/src/components/common/equity-chart.vue`、`frontend/src/views/ai/analysis/index.vue`、`frontend/src/views/ai/backtest/{index.vue,modules/backtest-detail-drawer.vue}`、`frontend/src/service/api/strategy.ts`、`frontend/src/typings/api/{strategy.d.ts,backtest.d.ts}`、`frontend/src/locales/langs/{zh-cn,en-us}.ts`、`frontend/src/typings/app.d.ts`
- 契约：`aiDoc/contracts/boundary.md`「绩效深化（P3，2026-09-16，迁移 0037）」

## 记录日期

2026-09-16
