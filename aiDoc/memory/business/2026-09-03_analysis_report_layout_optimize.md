# 分析策略与分析结果排版优化

## 需求描述

优化 AI 分析报告的"分析策略"（策略配置抽屉）与"分析结果"（报告正文）排版：共享报告面板 `analysis-report-panel.vue`（大盘/板块/资讯/轮动 4 页复用）+ 财报分析页，统一视觉风格、重构信息层级、消除重复代码。纯视觉/布局重组，不引入折叠/分 Tab 等结构变化。

## 状态

已完成

## 涉及范围

### 后端

无（不动接口契约、轮询逻辑、权限、路由、提示词 max_length=2000 上限）

### 前端

- 新增共享基础设施（`frontend/src/views/ai/`）：
  - `utils.ts` 增 `renderAnalysisMarkdown(raw)`：统一"剥离 ```json 摘要块 + `<think>` 块 → MarkdownIt 渲染"，md 单例（breaks+linkify、html:false），替代原先面板 1 处 + 财报页 2 处共 3 份重复逻辑
  - `components/analysis-markdown.vue`：props `{ raw }`，承载唯一一份 `.analysis-markdown` 排版样式（h2/h3 带左侧主色竖条、p/li 行高 24px、table/blockquote/hr/行内 code 样式、首尾子元素 margin 清除）
  - `components/analysis-status-view.vue`：三态占位（running 机器人图标 / failed NEmpty+errorMsg / empty NEmpty+emptyTip），统一原先 4 处重复
  - `components/analysis-section.vue`：区块标题容器（3px×14px 圆角主色竖条 + 13px/600 标题），替换 NDescriptions label 与裸加粗文本两种混用风格
  - `components/analysis-summary-card.vue`：摘要卡纯容器（rounded-8px 边框 + 浅底）
- `analysis-report-panel.vue` 重写模板层：
  - market 摘要卡：市场情绪 NTag + 市场温度（小圆环 NProgress + 着色数字）+ 总评文本
  - sector/rotation：轮动总结摘要卡（含标签）；主题热度/关注板块/近期轮动/明日候选/切换信号各成 AnalysisSection 区块
  - news：总评摘要卡 + 两分区（宏观行业/个股资讯）AnalysisSection
  - 明日研判条：主色浅染边框 + 左竖条
  - 策略抽屉：NForm 换 AnalysisSection 分组（研判设置/策略提示词/明日研判提示词），textarea 加 maxlength=2000 + show-count，资讯注入提示跟提示词组、生效说明置底
  - 轮询/历史/配置保存等全部逻辑不动
- `financial-analysis/index.vue`：删自带 MarkdownIt 与重复 CSS，接入 4 个共享组件；解读结果区改摘要卡（本期评级/下期预测评级/预测方向/报告期/行业 + forecast.summary）+ 统一区块标题（预测依据/券商预测对照/核心亮点/风险点）

## 约束与备注

- 摘要卡标签信息不能丢：老版 NDescriptions 有「轮动总结」「总评」label，重写时一度遗漏，已补回（视觉走查发现）
- app.d.ts 0024 批次有 14 个 aiAnalysis i18n 键漏同步（sessionClose/macroNewsLabel/newsInjectTip 等），导致历史基线虚高，本次补齐后 typecheck 39→24
- 剩余 24 个错误为无关基线（macro 模块 i18n 键、aiStrategy trailing 键、chat select 类型等）
- 验证方式：typecheck + 浏览器无头截图 5 页（大盘/板块/资讯/轮动/财报）+ 策略抽屉，逐页确认无重叠溢出

## 相关文件

- `frontend/src/views/ai/utils.ts`
- `frontend/src/views/ai/components/analysis-markdown.vue`（新）
- `frontend/src/views/ai/components/analysis-status-view.vue`（新）
- `frontend/src/views/ai/components/analysis-section.vue`（新）
- `frontend/src/views/ai/components/analysis-summary-card.vue`（新）
- `frontend/src/views/ai/components/analysis-report-panel.vue`
- `frontend/src/views/ai/financial-analysis/index.vue`
- `frontend/src/typings/app.d.ts`

## 记录日期

2026-09-03
