# 长期资讯采集标记 + AI 分析加权

## 需求描述

长期影响类资讯（如厄尔尼诺对农业/铜/煤/电的数月供给冲击）此前被当作近期消息处理：超过 24h/7d 时间窗就从 AI 分析素材中消失，窗口内又与普通快讯同权重。要求：采集时标记长期资讯，分析处理时额外考虑权重。

## 状态

已完成

## 涉及范围

### 后端

- 新增 `modules/admin/services/sys/news_tagger.py`：关键词规则打标器 `tag_long_term(title, summary)`，标签口径复用轮动 THEME_GROUPS 主题名；规则首批覆盖气候类（厄尔尼诺/拉尼娜/干旱等→农业牧渔/有色/煤/电）、有色/能源供给、产能政策、货币政策、贸易政策、猪周期六类；标题命中即标，仅摘要命中需 ≥2 关键词防误标
- `BusinessNews` 加列 `long_term_tags`（JSON 可空，空=短期资讯），迁移 `0031_news_long_term_tags`
- `news_sync_service.py` 入库行构造时打标（url 去重 on_conflict_do_nothing 意味着旧闻不重打，靠回填脚本覆盖）
- 回填脚本 `scripts/backfill_news_long_term_tags.py`（近 90 天存量，幂等；首次执行 179175 条命中 5957 条）
- `analysis_executor.py`：新增 `_collect_long_term_news`（近 90 天带标签资讯按标签分组、每组最新 3 条、总上限 20 条，独立成段附「中线背景而非当日催化/共振时提高权重并点明传导链」处理指令）；四类分析（market/sector/rotation/news）全部注入，且纳入摘除外部内容降级重试路径；news 早晚报/周报 prompt 加「长期事件跟踪/复盘」章节，sector/rotation prompt 补共振与持续性加成要求

### 前端

- 无改动（资讯列表标签徽标留作后续可选项）

## 约束与备注

- 一条多标签资讯会出现在多个分组（设计如此：标签维度各取所需），同事件多来源重复由 LLM 按既有「相似资讯合并」指令收敛
- 关键词打标存在误标（如反倾销类统一打 有色/化工/汽车 偏宽），后续按 badcase 补词
- 算法/提示词改动需重启后端生效；迁移需 `ENVIR=dev .venv/bin/alembic upgrade head`
- 长期线索段约 1000 字 / 20 条上限，不显著拉长 prompt

## 相关文件

- `backend/modules/admin/services/sys/news_tagger.py`（新）
- `backend/modules/admin/services/sys/news_sync_service.py`
- `backend/database/models/business/news.py`
- `backend/alembic/versions/0031_news_long_term_tags.py`（新）
- `backend/scripts/backfill_news_long_term_tags.py`（新）
- `backend/modules/analysis/services/analysis_executor.py`

## 记录日期

2026-09-09
