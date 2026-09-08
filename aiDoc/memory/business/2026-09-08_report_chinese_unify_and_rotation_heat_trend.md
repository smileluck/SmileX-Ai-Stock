# 分析报告中文统一 + 板块轮动策略热度/趋势权重

## 需求描述

1. AI 分析报告中总夹杂英文单词，要求尽量统一中文显示
2. 优化板块分析（轮动）策略，评分纳入热度与趋势权重

## 状态

已完成

## 涉及范围

### 后端

- `modules/analysis/services/analysis_executor.py`：
  - 新增 `_CHINESE_OUTPUT_RULE` 强约束，`_build_system_prompt()` 对全部 7 类报告 prompt（大盘/板块 × 收盘/早盘、资讯 morning/weekly、轮动）统一追加：正文与 JSON 文本字段一律简体中文、术语必须中文、禁止英文枚举码混入正文、仅允许 PE/ROE/CPI 等通用金融缩写
  - 轮动 prompt 正文中残留的 `(gathering)`/`(hot)` 改为中文表述（JSON schema 枚举码保留，供前端 tag 配色）
  - 新增 `_sanitize_report_language()` 兜底：LLM 返回后落库前，对开头 ```json 块之外的 markdown 正文做词边界替换（`_ENUM_ZH_MAP`：stage/action/signal/theme status/board_type 20 个英文码→中文），JSON 块保持原样
- `modules/stock/services/rotation_service.py`：
  - `_calc_factors` 新增 4 因子（全部用 `business_board_daily` 存量字段，无新抓取/无迁移）：`turnover_rate`/`turnover_ratio`（换手率相对 5 日均值倍数）、`breadth`（上涨家数占比）、`inflow_trend`（近 3 日净流入合计 − 前 3 日合计）、`momentum_accel`（近 3 日复合涨幅 − 前 7 日复合涨幅）
  - `_tomorrow_score` 新权重：换手温和放大(1-2倍)+4 / 剧烈放大(>3倍)且中高位 -4；宽度 ≥0.7 +5 / 上涨但 ≤0.3 -5；资金加速流入 +5 / 连续流入但衰竭 -5；动量加速且非高位 +3 / 高位减速 -3。评分仍收敛 0-100，`_decide_action` 阈值不变

### 前端

- 无改动（报告面板原样渲染；JSON 枚举码配色逻辑依赖英文码，刻意保留）

## 约束与备注

- 英文泄漏根因：轮动 prompt 字段口径/JSON 示例/注入的规则引擎 JSON 都含英文枚举原值，LLM 复述时带入正文；修复 = prompt 强约束（主）+ 落库前确定性替换（兜底）双保险
- `_sanitize_report_language` 必须跳过开头 ```json 代码块，否则前端 `analysis-report-panel.vue` 的 stage/status tag 配色（按英文码映射）会失效
- 换手率字段三数据源中仅东财/腾讯源有（同花顺源无），缺失时因子为 None 不参与加减分
- 算法仍是读时计算不入库，但需重启后端服务生效
- API 契约与 DB 结构均未变（新因子只进评分，不透出到 RotationOverviewItem）

## 相关文件

- `backend/modules/analysis/services/analysis_executor.py`
- `backend/modules/stock/services/rotation_service.py`
- `backend/database/models/business/stock_market.py`（turnover_rate/rising_count/falling_count 字段来源，未改）

## 记录日期

2026-09-08
