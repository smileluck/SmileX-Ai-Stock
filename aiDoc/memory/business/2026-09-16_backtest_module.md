# 策略回测模块

## 需求描述

新增「策略回测」模块（`backend/modules/backtest/`，前缀 `/admin/backtest`）：回放策略已记录的真实 AI 信号（`business_strategy_signal`），按 baostock 历史日线逐日模拟撮合，输出绩效汇总与净值曲线。明确不做 LLM 逐日重放（行情/资讯快照是当前值，重放存在前视偏差）。

## 状态

已完成

## 涉及范围

### 后端

- 新表（迁移 0033）：`business_backtest`（参数快照/三态状态/result 绩效汇总 JSON/equity_curve 净值曲线 JSON/started_at/finished_at）、`business_backtest_trade`（逐笔成交：action/trade_date/price/quantity/amount/fee/reason/return_rate）
- `services/engine.py` 纯函数回放引擎（不依赖 DB/网络，可独立 smoke）：信号次日开盘价成交（先卖后买再 adjust）、T+1、止损（跳空按 open）>目标价（涨停按 `limit_up_threshold` 暂缓顺延，回测不触发 AI 复核）>回撤止盈、止损/目标价 sanity 修正（`_sanitize_price_levels` 为 strategy 模块私有函数，引擎内实现等价逻辑并注明）、等权预算 `initial_capital/max_positions` 整手买入、佣金（万2.5 默认最低5元）+滑点（0.1%）+印花税（0.05% 仅卖出）、期末强平 backtest_end；绩效含 total/annual(252)/max_drawdown/sharpe(√252，样本<2 为 None)/win_rate/profit_factor(无亏损 None)/trade_count/warnings
- `services/market_data.py`：baostock 单连接串行（login/query/logout 同线程 + asyncio.to_thread，照 `_baostock.py` 模式），adjustflag="3" 不复权；股票版 `to_bs_stock_code`（6→sh，0/3→sz，4/8 北交所不支持记入 warnings 跳过，区别于指数专用 `to_bs_code`）；交易日历=上证指数 sh.000001 日线 date 序列；单次回测内存缓存，不建行情表
- `services/backtest_service.py`（CRUD + submit 校验：策略存在/start<end/≤3年/同策略 running 并发拒绝 11702）+ `services/backtest_runner.py`（照搬 strategy_executor 异步模式：spawn 后台任务 + 独立 session 只传 id + 900s wait_for 兜底 + 失败裸 UPDATE 回写 failed/error_msg）
- 接口：`POST /run`（异步提交即返 running 记录）、`GET /list`（分页，strategy_id/status 过滤，created_at 倒序）、`GET /{id}`（含 result+equity_curve）、`GET /{id}/trades`（成交明细分页，trade_date+id 升序）、`DELETE /{id}`（软删，running 拒绝）；权限复用 `strategy:manage`（未新增菜单/权限种子，超管与已有策略权限角色可直接用）
- 错误码 11701-11703（BACKTEST_NOT_FOUND/RUNNING_CONFLICT/INVALID_PARAMS），i18n 中英 yaml 与根 error_codes.md 已同步；`alembic/env.py` 补 backtest 模型导入

### 前端

- 页面 `views/ai/backtest/index.vue`（路由 `ai_backtest`，/ai/backtest）：顶部发起回测卡片（策略下拉复用 `fetchGetStrategyList`、日期区间默认近 6 个月禁选未来、初始资金，滑点/佣金/印花税收起在高级参数 NCollapse）+ 记录列表卡片（状态 tag、总收益/回撤/胜率/交易次数、详情/删除，运行中 10s 轮询——`useAutoRefresh` 的 `shouldRefresh` 闸门，`hasRunning` 为 false 即停）
- `modules/backtest-detail-drawer.vue`：绩效卡片网格（NStatistic×8）+ warnings NAlert + 收益曲线 + 成交明细分页表（running 时抽屉内同样 10s 轮询）；`modules/equity-chart.vue`：复用 `hooks/common/echarts` 的 `useEcharts` 画净值折线（含 inside+slider dataZoom，红涨绿跌）
- API `service/api/backtest.ts`（5 个 fetch* 函数，注册进 index.ts）+ 类型 `typings/api/backtest.d.ts`（Api.Backtest 命名空间，status 为字符串三态无需桥接）
- i18n `page.aiBacktest.*`（zh/en）+ route key `ai_backtest`，app.d.ts Schema 已同步
- 路由由 `@elegant-router/vue` vite 插件在构建时自动生成（meta title=key/i18nKey=route.key，icon/order 走后端菜单 DB 同 ai_analysis）；`pnpm gen-route`（sa gen-route）实为交互式新建页面脚手架，既有页面不适用
- 菜单项需后台菜单库手工新增（指向 /ai/backtest，权限可复用 strategy:manage）

## 约束与备注

- 信号源含 executed/skipped 等全部状态（回放的是信号意图而非实盘执行结果），关联 Run 排除已删除执行记录，按 run_date+id 升序
- 滑点只应用于信号驱动的买/卖成交价；止损/止盈/回撤/期末强平按规则价成交不再叠加滑点，但所有卖出都扣佣金+印花税
- 同日同时触及止损与目标价时保守按止损处理（先判止损）
- 僵死 running 回测（进程重启）当前无自动恢复，会阻塞同策略并发——后续可参照 trade_engine 的 STALE_RUN_MINUTES 模式补
- **坑（已于 2026-09-16 修复）**：`alembic/env.py` 模型靠显式 import 注册，曾缺失 BusinessStrategySignal/analysis/research/macro/financial 等多张表的导入——autogenerate 会把这些表生成 drop_table 及大量 comment 漂移。当日已补齐全部模型导入并落地迁移 `17203a828aab_sync_model_metadata_drift`（新建缺失的 sys_permission 表 + 消化全部 comment/索引命名漂移），之后 autogenerate 输出为空，不再需要手工清理

## 相关文件

- backend/database/models/business/backtest.py
- backend/modules/backtest/（router/endpoints/schemas/services：engine/market_data/backtest_service/backtest_runner）
- backend/alembic/versions/0033_add_backtest_module.py、backend/alembic/env.py
- backend/main.py、backend/core/response/response_code.py、backend/core/i18n/locales/{zh-CN,en-US}.yaml、error_codes.md

## 记录日期

2026-09-16
