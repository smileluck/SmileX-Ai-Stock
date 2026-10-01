# 每日资讯分析「长期主线」+ 主线 Tab + 因子处理

## 需求描述

每日资讯分析时分析出长期主线（半导体/光通信/房地产/厄尔尼诺/美联储/地缘冲突（美伊）），前端放新 tab「主线」，并增加因子处理。

## 状态

已完成

## 涉及范围

### 后端

- 迁移 `0050_news_mainline_tags.py`：`business_news` 新增 `mainline_tags`（JSON）；模型同步
- `news_tagger.py`：`MAINLINE_RULES` 注册表（主线名/关键词/映射轮动主题，初始 6 条）+ `tag_mainline()`（规则同 tag_long_term）+ `themes_to_mainlines()` 反查；`news_sync_service` 采集入库接线
- 回填：`scripts/backfill_news_mainline_tags.py`（近 90 天，幂等），已执行：279443 条命中 35602 条；近 7 天 6 主线全有量（地缘冲突/美联储/半导体最多）
- `analysis_executor.py`：`_collect_mainline_news`（近 7 天按主线分组，每组≤5 总≤30）仅 news/morning 注入并可随审核降级摘除；morning prompt 要求输出 `parsed_result.mainlines[]`（name/trend/summary/logic/related_sectors/news_count，≤8 条）；新增 JSON 纪律（字符串内禁英文双引号用「」）——曾因 LLM 输出未转义引号导致 parsed_result 解析失败
- 新接口 `GET /admin/analysis/news/mainlines`（`mainline_service.py`）：LLM 主线分析 + 注册表全量主线近 7 天分组资讯（count=0 也返回）
- 因子 DSL：`formula.py` 新增字段 `mainline_heat`（个股近5日关联主线资讯条数，常量序列）；`factor_calc._fetch_mainline_heat`（个股→板块快照→主题→主线反查→计数求和，失败降级不阻塞）；factor calc/screen 与 rule_executor 已接线；回测 series 按 0 处理附 warning

### 前端

- `views/ai/news-analysis/`：index.vue 加第三 tab「主线」（mainline 时不渲染 AnalysisReportPanel），新组件 `modules/mainline-panel.vue`（LLM 主线卡片 trend 着色 + 分组 NCollapse + 复用资讯详情抽屉）
- `service/api/analysis.ts` 加 `fetchGetNewsMainlines`；`typings/api/analysis.d.ts` 加 NewsMainline* 类型；`NewsParsedResult` 补 `mainlines`
- locale `page.aiAnalysis.mainline*`（zh/en）+ `typings/app.d.ts` Schema 同步（漏了会 TS2353）

## 约束与备注

- 主线清单为硬编码规则（后续运营化再考虑 sys_config/DB 化）；weekly 周报复盘不产出 mainlines
- 板块成分股快照只覆盖活跃板块，无归属个股 mainline_heat=0
- 验证：手动触发 news/morning 分析，parsed_result.mainlines 6 条主线齐全（trend/板块/条数）；/news/mainlines 接口 200 聚合正确；因子 IF(mainline_heat>100,1,0)+MA(close,5) 求值正确、series 回测 warning 正常；typecheck 无新增错误

## 相关文件

- `backend/alembic/versions/0050_news_mainline_tags.py`
- `backend/modules/admin/services/sys/news_tagger.py`、`news_sync_service.py`
- `backend/modules/analysis/services/{analysis_executor.py, mainline_service.py}`、`endpoints/analysis.py`、`schemas/analysis.py`
- `backend/modules/factor/services/{formula.py, factor_calc.py}`、`backend/modules/strategy/services/rule_executor.py`
- `backend/scripts/backfill_news_mainline_tags.py`
- `frontend/src/views/ai/news-analysis/{index.vue, modules/mainline-panel.vue}`
- `frontend/src/service/api/analysis.ts`、`frontend/src/typings/api/analysis.d.ts`、`frontend/src/typings/app.d.ts`、`frontend/src/locales/langs/{zh-cn,en-us}.ts`

## 记录日期

2026-10-01
