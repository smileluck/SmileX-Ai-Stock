<!-- last-updated: 2026-09-19 -->
# 策略执行链路并发与健壮性修复

> 执行计划：`aiDoc/plans/active/2026-09-19-strategy-execution-fixes.md`（含验收标准与回滚）

## 背景

2026-09-19 全量审查 strategy 模块 + 调度链路发现 4 高危（手动平仓 NameError、多 worker 调度器并发、手动触发绕过 max_instances、信号/持仓 lost update）+ 7 中危 + 若干低危，一次性修复。

## 变更要点

- **并发正确性**：信号 pending→终态、持仓 holding→closed 全部改条件 UPDATE（rowcount 判定认领）；`business_strategy_run` 加 `running_key` 生成列 + 唯一索引 `uq_strategy_run_running`（迁移 0039，MySQL VIRTUAL / PG STORED 分支），submit_run 捕获 IntegrityError 兜底 TOCTOU
- **调度器选主**：`scheduler/core/leader_lock.py` MySQL GET_LOCK 选主 + 20s ping 保活 + 故障转移（非 MySQL 方言 lockless 直通并告警多 worker 风险）；手动触发固定 job id + 执行期 per-task 锁预检；leader 侧 60s 周期 resync（follower 上任务 CRUD 靠它传播，RESYNC_JOB_ID 不被 sync 自删）
- **健壮性**：`_to_signal` 单条容错；行情连续 5 tick 为空结构化告警；交易日历 `stock/services/trading_calendar.py`（只有确定性结果可缓存）；rule 策略跳过 3% 偏差守卫；批处理单策略异常不中断整批；trade_engine timeout=240
- **规范**：runs 查询/执行器分流下沉 Service；分页走 `get_paginated_results`（page_size 上限 200，默认变 10）；track 接口拆出写权限 `strategy:position:track`（迁移 0039 种子按钮 ...8034，非通配角色需勾选）；裸 BaseModel 序列化豁免已记入 `aiDoc/contracts/boundary.md`
- **新错误码**：11512 POSITION_T1_LOCKED、11513 POSITION_PRICE_UNAVAILABLE（i18n 双语 + error_codes.md 已登记）
- **新任务**：`strategy.track_log_cleanup`（每日 03:23 分批清理 90 天前跟踪日志）；track log 改为价格变化/平仓/预警才写，停牌按小时节流

## 坑

见 `aiDoc/memory/lessons/2026-09-19-mysql-partial-unique-scheduler-leader.md`（生成列模拟部分唯一索引、max_instances 按 job id 生效、多 worker lifespan 选主、非确定性判定不缓存）。

## 上线注意

- 迁移 0039 前置：清理存量超时 running 脏数据（SQL 在迁移文件 docstring）
- 生产 MySQL 才走 GET_LOCK 选主；本机 dev 是 PostgreSQL，选主路径未真机验证
- 角色若不用通配权限，升级后需手工勾选新的「持仓跟踪」按钮权限
