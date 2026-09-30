# AI 推荐板块（AI 荐股）

## 需求描述

AI 助手下新增「推荐板块」：综合资讯热点、情绪（热榜）、因子、板块资金量、主力埋伏（大宗交易）、连板热门股六个维度，由 LLM 推荐 10 只最可能涨停（`limit_up`）或适合抄底（`bottom_fish`）的股票，给出预判买点/目标价/止损价；推荐结果自动落成策略买入信号，接入持仓追踪（交易引擎自动建仓跟踪）与回测（recorded_replay 零改动回放）。

## 状态

已完成

## 涉及范围

### 后端

- 新模块 `backend/modules/recommend/`（前缀 `/admin/recommend`）：`POST /run`（异步，权限 `recommend:run`）、`GET /latest`、`GET /runs`（分页）、`GET /runs/{id}`（权限 `recommend:list`）；错误码 11901/11902
- 新表 `business_recommend_run`（status 三态/ai_raw_response/parsed_result/candidate_snapshot/strategy_id）+ `business_recommend_stock`（rank 1-10、direction、score、buy_price/target_price/stop_loss_price、entry_type、reasons JSON 六维度、signal_id 回写），迁移 0040
- 生成范式仿 AnalysisExecutor：`_collect_candidates` 六维度确定性预筛（约 40 只候选）→ 单轮 LLM（场景 `STOCK_PICKING`）→ ```json 摘要 + markdown → 校验落库
- 信号桥接：固定策略「AI每日推荐」（prompt 型，max_positions=10，止损 5%/止盈 10%/回撤 5%），每次推荐建 `BusinessStrategyRun`（直接落 success 终态避开 running_key 唯一约束）+ 每股一条 pending 买入信号（ref_buy_price=预判买点，run_date 取当日）
- `business_strategy_signal` 加 `entry_type`（market/limit，迁移 0040）：交易引擎 buy 分支对 `limit` 信号仅当实时价 ≤ 买点才成交（保持 pending 等下一 tick），并跳过 3% 参考价偏差守卫；bottom_fish→limit、limit_up→market
- 调度任务 `recommend.daily_run`（cron `45 16 * * mon-fri`，收盘各同步任务之后），同日 success/running 去重
- 菜单种子迁移 0041：menu id 2942406616008035（name `ai_stock-recommend`，parent 8001，sort 11）+ 按钮 `recommend:list`/`recommend:run`

### 前端

- 新页面 `frontend/src/views/ai/stock-recommend/index.vue`（路由 `ai_stock-recommend`）：生成按钮（hasAuth recommend:run）+ 5s 轮询、10 只推荐主表（方向/综合分/买点/入场方式/六维依据 tag/理由）、AI 综合研判 markdown（复用 AnalysisMarkdown）、历史抽屉、头部「回测」「持仓」跳转入口
- API `service/api/recommend.ts` + 类型 `Api.Recommend.*`；i18n `page.aiRecommend.*`（43 键）+ `route.ai_stock-recommend`
- 目标页 query 消费（新模式首例）：`views/ai/backtest/index.vue` 消费 `query.strategy_id` 预填发起表单与列表筛选；`views/ai/analysis/index.vue` 消费 `query.tab=positions` 切持仓 tab + `strategy_id` 预筛选
- gen-route 未走交互 CLI（仅支持脚手架新目录），改为直接实例化 `@elegant-router/vue` 插件再生成四件套

## 约束与备注

- 「主力埋伏」维度无个股级主力资金流数据源，以大宗交易活跃榜（上榜频次+上榜后涨幅）+ 板块主力净流入代理，prompt 中说明口径
- limit 入场信号当日未触及买点则按现有机制次日 15:05 过期（推荐本身次日有效）
- LLM 输出校验：代码须 `\d{6}` 且在候选池内（防幻觉丢弃）、价格位 sanity（止损<买点<目标，不满足按 5%/10% 重算）、解析失败重试一次
- 因子维度用单次行情抓取算 bias20+rsi14（两次 FactorCalcService.calc 会抓两遍全池行情超时），`_FACTOR_FETCH_TIMEOUT=300s` 兜底降级
- 回测接入 = 专用策略 recorded_replay，推荐页「回测」跳回测页带 strategy_id，回测代码零改动

## 相关文件

- `backend/modules/recommend/`（router/endpoints/services/schemas）
- `backend/database/models/business/recommend.py`、`strategy.py`（entry_type）
- `backend/modules/strategy/services/trade_engine.py`（limit 买点成交）
- `backend/modules/scheduler/tasks/recommend_run.py`
- `backend/alembic/versions/0040_add_recommend_module.py`、`0041_seed_recommend_menu.py`
- `frontend/src/views/ai/stock-recommend/index.vue`、`frontend/src/service/api/recommend.ts`、`frontend/src/typings/api/recommend.d.ts`

## 记录日期

2026-09-29
