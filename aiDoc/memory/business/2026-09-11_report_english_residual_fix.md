# 报告英文残留根治（sanitize 双 bug 修复 + 历史数据修复）

## 需求描述

用户反馈轮动策略分析报告仍有英文穿插。排查发现 9/8 上线的 `_sanitize_report_language` 兜底替换自身有两个 bug，且英文来源比枚举码更多。

## 状态

已完成

## 涉及范围

### 后端

- `modules/analysis/services/analysis_executor.py`：
  - **bug1（JSON 块污染）**：MiniMax-M3 回复以 `<think>` 开头，json 块不在文本起始，`re.match` 锚定失败 → json 块被当正文，枚举码 `"stage": "ferment"` 被误替换为中文（前端 tag 配色依赖英文码，9/9-9/11 报告配色实际已坏）。修复：先剥 think 再用 `re.search` 定位首个 ```json 块保护
  - **bug2（词边界漏替换）**：`\b` 把中文字视为单词字符，"高低位split分歧"这类中英粘连无边界 → 正文英文码一个没换掉。修复：边界改用 ASCII 字母环视 `(?<![A-Za-z_])...(?![A-Za-z_])`
  - 新增剥 `<think>` 块（含未闭合）：防 20000 字入库截断后未闭合 think 在前端裸露英文
  - `_ENUM_ZH_MAP` 扩充注入数据字段名（position_pct→位置分位、heat→热度、score→评分、rank_change→排名跃升、gain_3d 等约 30 个）
- 新增 `scripts/repair_analysis_enum_codes.py`：修复被旧 sanitize 污染的历史 run——字段级反向映射恢复 json 块/parsed_result 英文码（退潮按字段分 ebb/cooling）+ 新版 sanitize 重跑正文。已对 9/8-9/11 的 14 个 rotation/sector run 执行完毕

### 前端

- 无改动

## 约束与备注

- **JSONB 更新三连坑**：嵌套原地修改不标脏；浅拷贝修复会同步污染"原值"导致赋值比对相等不标脏——必须 `copy.deepcopy` 后修改再整体重赋值（第一次修复脚本两连踩，parsed_result 两次都没写进去）
- 9/9 的 rotation 报告（run_id=3491777746509824）是截断单：20000 字几乎全是 think，修复后正文为空——属本来就损坏的数据，如需可在前端删除该条或重新生成
- MiniMax-M3 思考块的预算会挤占输出：该截断单就是 think 耗尽 20000 字符所致，配合 LLM 配置 max_tokens 上限可缓解
- uvicorn --reload 会自动加载改动，无需手动重启

## 相关文件

- `backend/modules/analysis/services/analysis_executor.py`
- `backend/scripts/repair_analysis_enum_codes.py`（新）

## 记录日期

2026-09-11
