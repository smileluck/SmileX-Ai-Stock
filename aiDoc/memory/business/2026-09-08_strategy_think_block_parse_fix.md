# 策略分析偶发失败修复（think 块干扰 JSON 解析）

## 需求描述

用户反馈「AI 分析中有些策略不执行了」。排查后确认：调度链路正常（12 个启用策略每日各时段均有执行记录），表象来自部分 run 随机失败——错误均为「无法从 AI 回复中解析出 JSON 数组」，近 5 个交易日每天 1~3 条，随机命中不同策略/时段。

## 状态

已完成

## 涉及范围

### 后端

- `modules/strategy/services/strategy_executor.py`：
  - `_extract_json_array` 解析前先剥离 `<think>...</think>` 思考块
  - `_analyze` 中 LLM 原文改为解析前独立 commit 落库；解析失败降级重试一次

### 前端

- 无改动

## 约束与备注

- 根因：智能选股场景（STOCK_PICKING）未绑定模型，回退默认模型 MiniMax-M3（思考模型），输出先带大段英文 `<think>` 块；解析兜底逻辑取「第一个 [ 到最后一个 ]」，think 块含方括号时混入思考文字导致 json.loads 失败——失败的随机性由此而来
- 加重因素：LLM 配置 max_tokens 为空（请求不带上限），思考过长时响应截断、JSON 缺闭合 `]`；近 3 天 58 条成功记录中 4 条顶到 20000 字符存储截断
- 伴生 bug：原文先赋值后解析，解析异常被外层 rollback 回滚，失败 run 的 ai_raw_response 全为空，无法取证——已改为解析前独立 commit 修复
- 未闭合 `<think>`（截断在思考块内）刻意不剥离：剥掉会留空文本静默返回空信号，保留抛错→重试更稳
- 可在「LLM 配置」给 MiniMax-M3 设 max_tokens 上限进一步降低截断概率（用户配置项，非代码）

## 相关文件

- `backend/modules/strategy/services/strategy_executor.py`
- `backend/modules/agent/services/llm_client.py`（stream_chat，未改）
- `backend/modules/scheduler/tasks/strategy_run.py`（调度逻辑，排查证明无问题，未改）

## 记录日期

2026-09-08
