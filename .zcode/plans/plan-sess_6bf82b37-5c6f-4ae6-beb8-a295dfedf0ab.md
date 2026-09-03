# 分析策略与分析结果排版优化方案

**范围**（用户已确认）：共享报告面板 `analysis-report-panel.vue`（大盘/板块/资讯/轮动 4 页受益）+ 财报分析页，统一风格并消除重复代码。
**力度**（用户已确认）：重构信息层级——纯视觉+布局重组，不改变结构化数据来源、接口契约和交互逻辑。

## 一、新增共享基础设施（去重）

1. **`frontend/src/views/ai/utils.ts`** 新增 `renderAnalysisMarkdown(raw: string): string`：统一"剥离开头 ```json 摘要块 + `<think>` 块 → MarkdownIt 渲染"逻辑（当前在面板 1 处 + 财报页 2 处重复，共 3 份），md 实例单例（breaks+linkify、html:false）。
2. **新建 `frontend/src/views/ai/components/analysis-markdown.vue`**：props `{ raw: string }`，内部调 `renderAnalysisMarkdown` 并 `v-html` 渲染，承载**唯一一份** `.analysis-markdown` scoped 样式（当前面板与财报页各复制一份完全相同的 CSS）。替换面板正文与财报页主报告区、历史详情抽屉共 3 处调用。
3. **新建 `frontend/src/views/ai/components/analysis-status-view.vue`**：三态占位组件，props `{ status: 'running'|'failed'|'empty', errorMsg?, emptyTip? }`，统一"生成中（机器人图标）/ 失败（NEmpty+error_msg）/ 无记录（NEmpty）"渲染（当前 4 处重复）。

## 二、报告面板排版重构（analysis-report-panel.vue）

**统一"区块标题"模式**（替换现在 NDescriptions label 与裸加粗文本两种混用风格）：
- 区块标题 = 左侧 3px×14px 圆角主色竖条 + 13px/600 文字，上距 16px 下距 8px；通过局部 class 或抽一个 `report-section` 结构实现，核心观察、资讯分区、轮动各区块全部套用。

**摘要区卡片化**（去掉 bordered NDescriptions 的表格感）：
- market：改为摘要卡（rounded 边框 + padding）：首行"市场情绪 NTag + 市场温度（小圆环+着色数字）"，次行总评文本。
- sector/rotation：轮动总结为文本块；"关注板块/主题热度/近期轮动/明日候选/切换信号"各成区块（复用现有 i18n 键），标签云与列表内容不变、仅换容器与间距。theme_heat 每行行距略放宽。
- news：总评文本块 + 两个分区沿用现有边框小卡列表，polish 间距。

**明日研判条**：在现有边框基础上加主色浅背景轻染（CSS 变量派生）+ 左侧竖条，圆角 8px。

**markdown 正文排版增强**（写入共享组件样式）：
- h2：15px/600 + 左侧 3px 主色竖条 + padding-left 8px，上距 18px；h3：14px/600 上距 14px
- p/li 行距 22→24px、段距 6→8px；`> :first-child` 清除顶部多余 margin
- 补充 table（th 浅色底）、blockquote、hr、行内 code 样式
- 底部"生成时间"行保持不变

**策略配置抽屉分组化**：
- 分"研判设置 / 提示词"两个视觉分组（套用区块标题样式），底部两行小字提示拆到各自分组下（资讯注入提示跟提示词组、生效说明置底）
- textarea 加 `maxlength + show-count`（对齐财报页现有做法）

## 三、财报页对齐（financial-analysis/index.vue）

- 删除自带 MarkdownIt 实例、`renderedMarkdown`/`drawerMarkdown`、整段 `.analysis-markdown` CSS，改用共享 `AnalysisMarkdown`（2 处）
- running/failed/empty 三态改用共享 `AnalysisStatusView`（2 处）
- 解读结果区（主区 + 历史详情抽屉）：顶部摘要卡（本期评级/下期评级/预测方向+摘要/报告期/行业），"预测依据/券商预测对照/核心亮点/风险点"套统一区块标题，替换现在的裸加粗标题
- 历史表格、筛选、查询卡不动

## 四、i18n 与文档

- 优先复用现有键，预计零新增；若实现中确需新键，同步 `zh-cn.ts` / `en-us.ts` / `app.d.ts` 三处
- 按 AGENTS.md 记忆规则：新增 `aiDoc/memory/business/2026-09-03_analysis_report_layout_optimize.md` 并更新需求索引

## 五、验证

- `pnpm typecheck`，与改动前基线对照（现有基线约 39 个既有错误，不新增）
- 启动/复用本地前端 dev 服务，浏览器无头截图大盘/板块/资讯/轮动/财报 5 个页面，逐页核对明暗两种主题下摘要卡、区块标题、markdown 排版无溢出错位；若本地服务不可用则退化为代码走查

## 不做的事

- 不动接口契约、轮询逻辑、权限、路由、后端
- 不引入折叠/分 Tab 等结构变化（用户未选）
- 不动 `/ai/analysis` 策略交易三 Tab 页面