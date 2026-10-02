# 系统功能审阅与修复（第 2 轮：日志竞态 + 任务残留 + 策略链路 12 项）

## 需求描述

用户要求继续审阅并优化系统功能、确保正确运行并给出优化建议（第 1 轮见 2026-10-02_system_review_query_param_fixes.md）。本轮经三路只读侦察（运行状态巡检 / 策略核心链路代码审阅 / 优化落点侦察）后全量修复。范围决策：全修（确定性缺陷 + 架构性优化）；昨天修复先独立提交（commit 2e40ff0）。

## 状态

已完成（代码已由热重载部署并逐项验证；日志竞态修复需重启 dev server 才完全生效，见「约束与备注」）

## 修复明细

### 批次 1：P0/P1 运行环境

1. **日志轮转双进程竞态（P0，已造成 09-30~10-01 全天日志丢失）**：reload 父进程与 worker 各在 import 期执行 `setup_logging()` → 两份 `logs/app.log` 轮转 handler，午夜双重轮转竞态（`DailyDirFileHandler.rotation_filename` 先 unlink 已存在归档 → 互相删档）。修复：`setup_registry.setup_app` 移除 `setup_logging()`，改在 `main.lifespan` 首行调用（仅真正服务进程配置文件 handler）。已验证：新代码 import 期 root 文件 handler 数=0。**旧父进程仍持旧 handler，需手动重启 dev server 退场**。
2. **任务 running 状态残留（P1）**：进程死亡后 `sys_scheduled_task.last_status` 与任务日志行永远停在 running（不阻塞调度，仅误导展示）。新增 `scheduler.recover_stale_running_tasks`：leader 启动时把超 2 小时的 running 置 failed（阈值覆盖最长任务 timeout 900s，避开他 worker 手动触发中的任务）。**已实跑**：部署后首轮清扫 37 行残留（rotation_stock_sync、多个 trade_engine tick），该任务当日 15:38 恢复 success。

### 批次 2：核心链路确定性缺陷

3. **守卫漏网**（trade_engine buy 分支）：原 `elif sig.ref_buy_price and ...` 使 prompt 型 buy 缺 ref_buy_price 时**完全绕过 3% 偏差守卫**无锚建仓。改为 `elif strategy.strategy_type != "rule"`：prompt 型缺/非法参考价直接 claim skipped 拒单（recommend 信号恒带 buy_price 不受影响）。
4. **pct=0 陷阱**（trade_engine._sanitize_price_levels + backtest/engine.py 同款）：`stop_loss_pct/take_profit_pct=0` 时按 0 重算出「止损=买价」→ 建仓下一 tick 即触发平仓。改为 `not in (None, 0)` 视同未配置（返回 None 交由跟踪逻辑处理）。**未改 schema gt=0**：存量策略可能配 0，改校验会阻塞无关编辑（见建议清单）。
5. **落库前实时价校验**（strategy_executor._analyze 新增 5.5 步）：无池策略 LLM 自选股不在快照（池∪持仓）→ buy 参考价无锚。补拉缺失行情；缺价丢弃该条；参考价缺失/非法/偏差>3% 时重锚为实时价、清掉 LLM 价格位（交由 trade_engine 按 pct 重算）、reason 标注原值；`run.parsed_signals` 反映校验后信号。
6. **ETF/可转债前缀**（quote_helper._to_sina_code）：补 "5"→sh（沪 ETF）、"1"→sz（深 ETF/可转债）映射，池内此类标的原先永远拿不到行情。
7. **除法守卫**（strategy_executor 浮盈上下文行）：`h.buy_price > 0` 防脏数据除零。

### 批次 3：架构性优化

8. **idle-in-transaction 重构（4 处）**：`strategy_executor._analyze`（读快照后 commit 再进 600s LLM）、`rule_executor._evaluate`（commit 再进行情抓取）、`backtest_runner._recorded_signals` 与 `_rule_prepare`（commit 再进 fetch_market_data 900s）。依赖 `expire_on_commit=False`（已确认）保证已读属性可用。集成验证：_recorded_signals 真实跑通 select→commit→网络降级抓取→返回。
9. **tick 跨进程互斥**（trade_engine 3.5 步）：维护 commit 后 `pg_advisory_xact_lock(TICK_ADVISORY_LOCK_KEY=9150110001)`，把「快照加载→执行→落库」整段跨进程串行化（tick 末次 commit 自动释放）。消除手动补跑与 cron tick 并行时 max_positions 竞态（单进程内本有 max_instances=1）。锁语义已验证（持锁阻塞/提交释放）。
10. **僵死占位锁就地接管（2 处）**：`strategy_executor.submit_run` 与 `backtest_service` 创建路径的冲突分支，遇超时（15/20 分钟）running 记录时条件 UPDATE 置 failed 后继续创建新记录——消除晚间/周末被占位锁阻塞到次交易日的问题（原恢复逻辑只在交易时段的 tick 里跑）。SQL 语义已真库验证（stale 判定/条件接管/并发互斥）。

### 侦察修正（认知层面）

- uvicorn 0.40 默认只对 `*.py` 热重载，第 1 轮"日志写入触发 214 次重启"结论有误（已修正第 1 轮文档）；`reload_includes` 保留为显式化无害配置。
- 第 1 轮建议的"实时行情注入+3% 偏差守卫"实为 2026-08-28 已上线（commit 8d13f8c），本轮真实缺口是无池策略自选股不在快照（已由第 5 项修复）。

## 验证结论

- 纯函数单测 13/13（pct=0 双端、价格位方向、ETF/可转债/存量前缀映射）
- 咨询锁语义 2/2（持锁阻塞、提交释放）
- 僵死接管 4/4（stale 判定、条件命中、二次互斥、造数清理）
- 事务边界集成 1/1（_recorded_signals 真实网络降级路径）
- 热重载后 4 个核心接口 200、今日日志 0 Traceback/0 500/0 422
- 批次 1.2 清扫实跑生效（37 行残留被清理）

## 优化建议清单（本轮未实施）

1. **重启 backend dev server**（P0，用户操作）：让日志竞态修复完全生效（旧父进程仍持一份旧 handler，午夜仍会竞态一次）。
2. 信号缺价重试上限：缺价信号最长 pending 约 2 个交易日，可加 retry 计数字段过期清理。
3. rule 型隔夜缺口守卫：rule 信号跳过偏差守卫，隔夜跳空无保护，可加基于 D-1 收盘的宽松缺口检查（如 >10% 拒单）。
4. 回测与实盘建仓数量口径统一（回测等权预算整手 vs 实盘固定 100 股）。
5. 研报抓取空 DataFrame 容错（akshare `stock_research_report_em` 午夜返回缺 infoCode 列，KeyError 已被捕获为 WARNING，建议跳过或调整抓取时点）。
6. backtest running 去重补 DB 唯一键兜底（当前仅 SELECT 预检，接管逻辑已缓解）。
7. `DATABASE__ECHO=True` 的 SQL 全量日志建议关闭（15 分钟 3.9MB，放大轮转竞态破坏面）。
8. `.env` 的 `DATABASE__URL` 用户名 posgres typo（实际 postgres）与库名 smilex_cloud（实际 smilex_ai_stock）——修改前需核实运行时配置加载链。
9. `_sanitize_price_levels` 可加下界校验（AI 给 0.01 这类"合法但荒谬"止损价等于无止损）。

## 约束与备注

- 无 DB 迁移；全部改动向后兼容。
- 守卫拒单会让"LLM 不按快照出价"从静默建仓变为显式 skipped 留痕，短期 skipped 占比可能上升——这是期望行为（暴露信号质量问题）。
- 新代码已由热重载部署；旧 reloader 父进程（9-30 启动）仍持有旧 logging 配置。

## 相关文件

backend/main.py、core/registry/setup_registry.py、modules/scheduler/core/scheduler.py、modules/strategy/services/{strategy_executor,trade_engine,rule_executor,quote_helper}.py、modules/backtest/services/{backtest_runner,backtest_service,engine}.py

## 记录日期

2026-10-02
