# 交易时机纪律落地：开盘日才交易 + 休市日误买入清理

## 需求描述

用户规则：非开盘日不建仓/不操作，A 股个股 T+1 卖出，支持 T+0 的 ETF 例外。排查发现系统不满足：交易日历在长假期间 fail-open，策略（含 AI 推荐）在休市日按陈旧收盘价自动购入持仓。

## 状态

已完成

## 根因与修复

### 根因

- `trading_calendar.py` 指数日线推断的"日历陈旧降级"以 `_prev_weekday`（上一自然工作日）为锚：长假第 2 个工作日起（如 10-02 周五，其上一工作日 10-01 也是节假日）必误判为交易日
- 新浪行情休市日照常返回上一交易日收盘价快照，行情层无日期新鲜度校验 → 交易引擎按陈旧价假成交
- recommend 全链路（调度 + 手动）无交易日守卫；手动策略 run 无守卫
- 信号有效期按自然日作废，跨长假时"保留至下一交易日"不成立

### 修复（改动点）

1. **交易日历接入 FQGate 权威日历**（`modules/stock/services/trading_calendar.py`）：判定链第一层改 `core.fqgate.calendar.trading_days`（交易所发布日历、含未来日期、无需登录），查询窗口判定日 -30/+15 天，返回须覆盖判定日否则降级；权威结果 True/False 均可缓存。指数日线推断降为第二层（长假误判局限写入 docstring，由行情新鲜度兜底）
2. **信号有效期改交易日口径**（`trade_engine.py`）：非交易日不作废 pending 信号，节前信号活到下一交易日 15:05；`_in_trading_hours` 改接收每 tick 预计算的 `today_is_trading`，避免降级路径重复拉日历
3. **行情双保险**（`quote_helper.py`）：非交易日硬闸（源头返回空，覆盖 FQGate 报价无 trade_date 的路径）+ 逐票新鲜度校验（trade_date 非当日剔除）；所有调用方（交易引擎/持仓跟踪/手动平仓取价/执行器快照）语义兼容"陈旧=缺席"
4. **recommend 调度守卫**（`scheduler/tasks/recommend_run.py`）：非交易日直接跳过
5. **手动触发拒绝**：策略 run 端点 + 推荐 run 端点非交易日抛 CustomError；新错误码 11514 STRATEGY_NON_TRADING_DAY / 11903 RECOMMEND_NON_TRADING_DAY（i18n 双语 + error_codes.md 同步）

### 存量清理（scripts/cleanup_nontrading_day_trades.py，已 --apply）

- A 类（非交易日买入）9 笔软删：10-02 误建仓 5 笔（巨人网络/华曙高科/国轩高科/比亚迪/药明康德）+ 09-25 中秋节误建仓 4 笔（中国石油/东方中科/雷科防务/美的集团）
- C 类（非交易日生成的 pending 信号）15 条置 expired（10 条 AI 每日推荐 + 5 条 rule 策略），否则会活到 10-08 开盘被误执行
- B 类（非交易日卖出）0 笔；run opened_count 修正 6 条
- 踩坑：持仓 buy_time 是 UTC 存储，比较前须转日期；FQGate 日历查询 end 落在假期内时 records 只到节前最后交易日，非截断

## 涉及范围

### 后端

- `modules/stock/services/trading_calendar.py`（FQGate 权威日历层 `_resolve_by_fqgate_calendar`）
- `modules/strategy/services/trade_engine.py`（有效期口径、`_in_trading_hours` 签名）
- `modules/strategy/services/quote_helper.py`（非交易日硬闸 + `_filter_fresh`）
- `modules/scheduler/tasks/recommend_run.py`（守卫）
- `modules/strategy/endpoints/strategy.py`、`modules/recommend/endpoints/recommend.py`（手动拒绝）
- `core/response/response_code.py`、`core/i18n/locales/*.yaml`、`error_codes.md`（11514/11903）
- `scripts/cleanup_nontrading_day_trades.py`（新增，dry-run 默认 + --apply）

### 前端

无改动（错误消息由后端统一响应直出）

## 约束与备注

- 纪律原文已存长期记忆 `aiDoc/memory/long-term/trading-timing-discipline.md`
- T+1 锁定（`position_service.py` 三处）此前已完整，本次未改
- 已知可接受边界：交易日 9:30:00 首个 tick 若新浪日期未翻当日，最多跳过 1 分钟
- 修复需重启后端生效（已于 10-02 当晚重启）；FQGate 网关在长假期间保持运行是权威日历生效的前提，网关停用时回退指数日线推断（长假仍有误判可能，行情新鲜度校验兜底不成交）

## 相关文件

见上「改动点」与「涉及范围」

## 记录日期

2026-10-02
