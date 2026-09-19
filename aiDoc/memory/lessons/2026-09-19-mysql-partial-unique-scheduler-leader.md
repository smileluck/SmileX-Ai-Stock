<!-- last-updated: 2026-09-19 -->
<!-- lesson-meta: status=pending count=1 post=0 target= -->
# MySQL 并发唯一约束与多 worker 调度器选主

## 情境

2026-09-19 策略执行链路修复（计划 `aiDoc/plans/active/2026-09-19-strategy-execution-fixes.md`）：防止多 worker/并发下重复 running 记录与调度器重复启动。

## 坑 / 模式

1. **MySQL 没有部分唯一索引（WHERE 子句）**，「同策略只允许一条 status=running」这类条件唯一约束要用**生成列模拟**：`running_key BIGINT GENERATED ALWAYS AS (CASE WHEN status='running' THEN strategy_id ELSE NULL END) VIRTUAL` + 唯一索引——唯一索引允许多个 NULL，非 running 行不占键位。PostgreSQL 仅支持 STORED 生成列，迁移需按方言分支。表达式用 `CASE WHEN` 不用 `IF()`（PG 无 IF 函数）。
2. **APScheduler 的 `max_instances=1` 按 job id 生效**：手动触发若每次生成新 job id（带时间戳），并发防护形同虚设。一次性 DateTrigger 的 job 开始执行即从 jobstore 移除，"不重复"还需执行期预检（进程内 per-task asyncio.Lock）。
3. **gunicorn 多 worker 每个进程都会跑 lifespan**：调度器/后台任务的启动必须有选主机制。MySQL 下用 `GET_LOCK`（连接断开自动释放，天然带故障转移）+ 专用持锁连接 + 周期 ping；选主后还要考虑 **follower 上的写操作如何传播到 leader**（本次用 leader 侧 60s 周期 resync 自愈）。
4. **缓存"非确定性"判定的结果会放大故障**：交易日历的盘前宽限/数据源降级结果若被整日缓存，会把暂时性不确定固化为整日错误（假日假成交 / 交易日风控失效）。只有确定性结果才允许缓存。

## 出现次数

1（2026-09-19 策略链路修复）

## 状态

pending

## 晋升去向

（待同类问题再次出现后晋升）

## 晋升后复发

0

## 记录日期

2026-09-19
