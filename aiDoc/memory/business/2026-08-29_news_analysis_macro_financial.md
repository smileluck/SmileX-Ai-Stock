# 每日资讯分析 + 宏观指数 + 财报解读

## 需求描述

三大新能力（迁移 0026）：

1. **AI 每日资讯分析**：早盘（交易日 9:25）+ 周日晚（20:30）两个时段对聚合资讯做分类解读，区分「宏观经济/行业资讯」与「个股资讯」两个分类，各不超过 10 条
2. **企业财报获取/解读/预测**：持仓+策略标的定时自动解读 + 任意股票手动查询解读，AI 输出财报质量评级/亮点/风险/下期预测
3. **宏观经济指数板块**：中美 CPI/PPI/M1/M2 等指标独立展示（卡片+走势图）+ 注入 AI 分析（大盘/资讯）

## 状态

已完成（2026-08-29）

### 后续增强（2026-09-01）

- 财报解读右侧抽屉展示本期评级 + 下期预测评级
- 解读记录列表（`financial-analysis/index.vue` historyColumns）在「报告期」后新增「本期评级」「下期预测」两列：数据取列表接口已返回的 `parsed_result`（quality_rating / next_quality_rating / forecast.direction），纯前端改动；仅 status=success 时显示 Tag，否则占位「-」；下期预测列 = 下期预测评级 Tag + 方向 Tag（改善/持平/恶化）
- 解读记录列表新增两个筛选下拉：本期评级（优秀/良好/一般/较差）+ 下期预测（改善/持平/恶化）。后端 `/admin/financial/interpretations` 加 `quality_rating` / `forecast_direction` query 参数（Annotated+BeforeValidator 枚举归一，非法值归 None 不过滤），JSON 列过滤用 `parsed_result['quality_rating'].as_string()` / `parsed_result['forecast']['direction'].as_string()`（json 列不支持 `?` 操作符）
- 重要数据事实：截至 2026-09-01 存量 60 条解读记录 `next_quality_rating` 均为 NULL（旧模型省略该字段）——下期筛选因此按 forecast.direction 实现；prompt 强化为「必须包含全部 6 个字段」后已实测生效（600519 新解读 parsed_result.next_quality_rating=良好）。注意该字段无独立列/接口字段，前端直接读 `parsed_result.next_quality_rating`

### 后续增强（2026-09-01 第二批：列表元信息 + 来源分析 + 策略配置化，迁移 0029）

- **股票名称/所属行业**：列表「股票」列改两行（名称 + 代码小字），新增「所属行业」列。根因修复：新浪财报接口「股票名称」列偶为空 → fetcher 加新浪行情兜底；`interpretation` 加 `industry` 列；创建解读时 `_resolve_stock_meta`（研报表最新非空 → 东财 push2 httpx 直连 f57/f58/f127，主源限流走 push2delay → 新浪名称最终兜底）；迁移 0029 对存量回填（60/60 覆盖，研报未覆盖 32 只由 push2 一次性脚本补齐）
- **下期盈利增长预测来源分析（两者都要）**：① prompt forecast 加 `drivers: string[]`（2-4 条驱动因素），列表「下期预测」Tag hover NPopover + 顶部卡/抽屉展示；② 券商对照：列表/详情接口对本页 code 集合查 `business_research_report` 每股最新一条（order_by published_date desc nullslast），组装 `research_brief: {org_name, rating, published_date, forecast{年份:{eps,pe}}}` 附到行，popover 与抽屉展示（约半数个股有研报覆盖）
- **分析策略配置化**：原硬编码 `_FINANCIAL_SYSTEM_PROMPT` 之上，新增单行配置表 `business_financial_config.prompt_template`（Text, ≤2000 字），`GET/PUT /admin/financial/config`（financial:list / financial:run），`_interpret` user prompt 尾部注入「分析策略要求（用户定制，生成时必须遵循）」；前端查询卡「分析策略」按钮（financial:run 可见）→ 抽屉 textarea 保存。端到端实测：策略「重点关注现金流与分红能力」成功注入（raw think 首句即提及，drivers 含分红相关条目）

## 涉及范围

### 后端

- analysis 模块扩展：`ANALYSIS_TYPES` 加 `news`、`SESSION_TYPES` 加 `weekly`，类型×时段组合校验（`VALID_TYPE_SESSIONS`）；`analysis_executor.py` 新增 news 两套 system prompt + `_collect_macro_context()` 宏观注入（market/news，失败可摘除降级）
- 新模块 `modules/macro/`：akshare 抓取（中国 CPI/PPI/货币供应、美国 CPI）→ `business_macro_indicator` upsert；任务 `macro.sync_all`（每日 07:30）
- 新模块 `modules/financial/`：akshare 新浪财务指标抓取 → `business_financial_report`；`FinancialService.submit_interpretation` 异步 AI 解读（与 AnalysisExecutor 同模式：三态 + 并发守卫 + 后台任务强引用）；任务 `financial.auto_interpret`（工作日 08:00，持仓+近30天信号标的，同报告期去重）
- 新表：`business_macro_indicator` / `business_financial_report` / `business_financial_interpretation`
- 错误码：11621（macro）、11641-11644（financial）；main.py 注册两路由 + 两调度任务

### 前端

- 新页面：`views/ai/news-analysis/`（morning/weekly tab，复用 analysis-report-panel）、`views/ai/macro/`（中美 tab + 指标卡片 + ECharts）、`views/ai/financial-analysis/`（代码查询 + 解读报告 + 指标表 + 历史列表）
- `analysis-report-panel.vue` 扩展 news 类型渲染（两个分类列表卡片，各 ≤10 条；策略抽屉隐藏研判开关）
- 新 API：`service/api/macro.ts`、`financial.ts`；类型 `Api.Macro.*` / `Api.Financial.*` / `Api.Analysis.NewsParsedResult`
- 菜单（迁移 0026）：`ai_news-analysis`（复用 analysis 权限）、`ai_financial-analysis`（financial:list/run）、`ai_macro`（macro:list/sync）

## 约束与备注

- news 分析 morning 取近 24h 资讯 60 条、weekly 取近 7 天 120 条（素材量大于输出上限，供 LLM 筛选）
- APScheduler 星期字段必须写 `sun`/`mon-fri`（数字是错位的）
- MappedAsDataclass 新表字段顺序：无默认值字段必须在有默认值字段之前（BusinessFinancialReport/Interpretation 踩过）
- 迁移菜单插入用逐行 insert（bulk_insert 首行键编译列丢值坑）
- 宏观/财报 akshare 列名做容错映射（上游列名偶有调整）
- 财报解读 LLM 复用 `analysis_executor._run_llm`（TREND_PREDICTION 函数模型）

## 相关文件

- `backend/modules/analysis/services/analysis_executor.py`（news prompt + 宏观注入）
- `backend/modules/macro/`、`backend/modules/financial/`
- `backend/modules/scheduler/tasks/analysis_run.py` / `macro_sync.py` / `financial_run.py`
- `backend/alembic/versions/0026_macro_financial_news.py`、`0029_financial_list_enhance.py`（industry 列 + 存量元信息回填 + business_financial_config 表）
- `frontend/src/views/ai/news-analysis/`、`macro/`、`financial-analysis/`
- `aiDoc/frontend-backend/boundary.md`（新增三段契约）

## 记录日期

2026-08-29
