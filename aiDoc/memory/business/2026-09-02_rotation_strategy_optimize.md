# 轮动策略优化：主题级聚合 + 评分重写（军工轮动漏判修复）

## 需求描述

2026-09-02 板块轮动到军工，策略未提前识别。用户要求优化。

诊断结论（当日实测数据）：原策略逐板块独立评分，看不见主题级资金集结——军工 19 个兄弟板块近 3 日 95% 上涨、平均位置分位仅 0.28，昨日数据已含明确信号，但单板块分数被埋没（军工电子Ⅱ 75 / 航空装备Ⅱ 65，远离榜首）；同时两类误报抬高：小概念排名跃升噪音（禽流感 rank_change 157 → 90 分霸榜）、龙头独行（通用设备 -2.16% 却 7 家涨停 → 81 分）。

## 方案（读时算不入库，算法改动无需重写数据）

1. **主题聚合**：`THEME_GROUPS` 18 个主题关键词映射（互斥设计：军工不吞裸「航空」，航空机场/航空运输归交通物流）；`_board_theme` 子串匹配归类，行业+概念两类板块合并聚合
2. **主题热度** `heat = 40*近3日上涨占比 + 25*min(1, 5日均涨幅/5) + 20*资金流入占比 + 15*(1-平均位置)`；状态 gathering（集结升温）/active（发酵走强）/hot（高位过热）/cooling（退潮）/flat
3. **评分重写**：`rank_pct` 分位数替代原始排名阈值（统一 ~124 行业 vs ~801 概念两类口径）；主题增强：gathering 主题 ≥3 成员 +10（inflow_ratio≥0.55 再 +4）＝提前埋伏信号，hot 主题中高位成员（位置≥0.6）-5 ＝兑现风险；新增「资金潜伏型启动」（inflow_days≥4 且 5 日涨 3-6% 且未深跌且非高位）
4. **噪音抑制**：3 日涨幅 <1% 时排名跃升加分减半（微概念排名抖动）；板块指数下跌时涨停梯队加分减半（龙头独行背离）
5. **涨停梯队跨类目匹配**：归一化板块名（去 Ⅱ/Ⅲ 后缀）UNION 成分股快照 stock_code 双通道（腾讯 pt0 板块名 vs 东财涨停池行业名）
6. **契约扩展**：overview 返回 `themes[]` + items 增 `theme/position_pct`；AI prompt 注入主题热度摘要（前10）+ 主题状态口径 + `theme_heat[{theme,status,heat,viewpoint}]` JSON 字段 + markdown 章节「主题热度与资金集结」

## 验证（诊断脚本实测，脚本已删）

军工主题 gathering 热度 74（19 成员 / rising_ratio_3d 0.95 / 位置 0.28）；军工信息化 91、北斗导航、无人机入概念 TOP10；军工电子Ⅱ 79 / 航空装备Ⅱ 77 入行业 TOP10；地面兵装Ⅱ（当日涨幅第一、昨日已 rank5）正确判 climax 主攻；禽流感类小概念噪音被抑制；农业牧渔 88 active / 金融 84 hot 判定合理。

## 前端

- `rotation-analysis/index.vue`：表格上方「主题热度条」（checkable NTag，点击筛选近期轮动/明日候选两表）；近期轮动表加 主题/位置 列，明日候选表加主题列
- `analysis-report-panel.vue`：theme_heat 摘要行（主题+热度彩色 tag + viewpoint，gathering蓝/active橙/hot红/cooling绿）
- i18n 三处新增 9 键（themeHeatTitle/themeCol/positionCol/themeStatus_*/themeHeatLabel）；typecheck 39 = 基线无新增

## 约束与备注

- 服务重启后新评分/新 prompt 才生效（当日收盘 rotation AI 报告需重启后手动触发或等待次日）
- 已知局限：QQ 独有板块（玉米/棉花等）无法解析东财代码缺历史，不参与部分指标

## 相关文件

- backend/modules/stock/services/rotation_service.py（THEME_GROUPS/_classify_stage/_tomorrow_score/_calc_theme_heat/_load_series/_load_limit_up_index/_calc_factors/get_overview）
- backend/modules/stock/schemas/rotation.py（RotationThemeItem、items 扩展）
- backend/modules/analysis/services/analysis_executor.py（主题数据注入 + 系统提示词 theme_heat）
- frontend/src/views/ai/rotation-analysis/index.vue、views/ai/components/analysis-report-panel.vue、typings/api/{stock-rotation,analysis}.d.ts

## 记录日期

2026-09-02
