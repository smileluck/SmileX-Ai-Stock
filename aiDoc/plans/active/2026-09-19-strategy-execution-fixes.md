<!-- last-updated: 2026-09-19 -->
# 策略执行链路修复（并发正确性 + 分层规范）

> 来源：2026-09-19 对 `backend/modules/strategy/` 全模块、调度入口、部署配置的审查。
> 方案已确认：调度器选主用 MySQL 命名锁（GET_LOCK）；全部问题纳入，分 P0/P1/P2/P3 阶段执行。

## 目标

- 消除策略执行链路的高危缺陷：手动平仓 NameError、多 worker 调度器并发、手动触发并发、信号/持仓 lost update、重复提交分析
- 修复中危健壮性问题：LLM 脏数据容错、行情降级告警、交易日历、规则策略偏差守卫口径、批处理容错
- 对齐分层/分页/权限/契约规范，清理低危坏味道

## 非目标

- 不引入资金/手续费模型（当前纯比例模拟盘为设计现状）
- 不改前端交互与页面结构（仅核对契约不受影响）
- 不重构交易引擎整体架构

## 假设

- 生产数据库为 MySQL（aiomysql 驱动），支持 GET_LOCK 与生成列
- 部署使用 gunicorn 多 worker（默认 4），worker 数不固定
- 迁移执行前需先清理存量重复 running 脏数据

## 影响面

- 后端：scheduler 模块（core）、strategy 模块（全部层）、stock 模块（公开行情封装）、alembic 迁移、main.py 生命周期
- 契约：`strategy:position:track` 权限码新增；分页参数上限对齐；其余字段契约不变
- 文档：aiDoc/contracts、memory/lessons

## 验收标准

- [ ] 手动平仓不传 price 正常执行（不再 NameError）
- [ ] 多 worker 启动时只有一个进程运行调度器；杀掉持锁进程后另一进程接管
- [ ] 同一任务手动触发与 cron tick 不并发；连点两次手动触发只执行一次
- [ ] 同一 pending 信号并发两个 tick 只成交一笔；并发 submit_run 第二次必抛 STRATEGY_ALREADY_RUNNING
- [ ] alembic upgrade head 可执行；重复 running 被 DB 唯一约束拒绝
- [ ] LLM 返回非数字价格时单条跳过，整轮分析不再整体失败
- [ ] `cd backend && uv run python -c "import main"` 通过

## 工作项

| # | 工作项 | owner | 依赖 | 建议写范围 | 验证命令 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 调度器选主 leader_lock.py + main.py 守卫 | AI | 无 | scheduler/core/leader_lock.py、main.py | `GUNICORN_WORKERS=2` 起服务看日志 | 完成 |
| 2 | 手动触发串行化（固定 job id + per-task Lock） | AI | 无 | scheduler/core/scheduler.py | 连点触发观察日志 | 完成 |
| 3 | 信号/持仓条件 UPDATE | AI | 无 | strategy/services/trade_engine.py、position_service.py | 并发 tick 断言单笔成交 | 完成 |
| 4 | Run running 生成列唯一索引迁移 + IntegrityError 兜底 | AI | 脏数据清理 | alembic/versions/、strategy_executor.py、rule_executor.py | `uv run alembic upgrade head` | 完成 |
| 5 | 手动平仓 fetch_latest_prices 导入修复 | AI | 无 | position_service.py | import 检查 | 完成 |
| 6 | _to_signal 单条容错 | AI | 无 | strategy_executor.py、rule_executor.py | 构造脏数据调用 | 完成 |
| 7 | 行情降级告警 | AI | 无 | trade_engine.py | 断行情观察日志 | 完成 |
| 8 | 交易日历接入 | AI | 无 | trade_engine.py、tasks/strategy_run.py、（复用 backtest/services/market_data.py 能力） | 休市日 tick 不成交 | 完成 |
| 9 | rule 策略跳过偏差守卫 | AI | 无 | trade_engine.py | 构造高开 rule 信号 | 完成 |
| 10 | strategy_run_execute 批处理容错 + trade_engine 显式 timeout | AI | 无 | tasks/strategy_run.py | 构造单策略异常 | 完成 |
| 11 | Endpoint 分层下沉 + 分页统一 + track 权限修正 | AI | #3 部分 | endpoints/strategy.py、endpoints/position.py、strategy_service.py | Swagger 行为不变 | 完成 |
| 12 | 手动平仓无价拒绝 / adjust 只许上调止损+记 executed_price / track log 条件化+清理任务 / 除零守卫 | AI | #3 | position_service.py、trade_engine.py、scheduler 清理任务 | 边界场景调用 | 完成 |
| 13 | 杂项清理（死代码/导入/错误码语义/quote_helper 公开依赖/内存热点） | AI | #11 | schemas、endpoints、quote_helper、stock services、strategy_service | import 检查 | 完成 |
| 14 | 契约豁免说明写入 aiDoc/contracts/boundary.md | AI | #11 | aiDoc/contracts/ | 文档评审 | 完成 |

## 验证命令

```bash
cd backend && uv run python -c "import main"
cd backend && uv run alembic upgrade head
GUNICORN_WORKERS=2 uv run gunicorn main:app -c gunicorn.conf.py  # 观察只有 leader 启动调度器
```

端到端：策略手动执行 → 信号生成 → tick 建仓 → 手动平仓（不传价）→ 正常成交；并发触发不重复建仓。

## 回滚 / 迁移

- 代码回滚：git revert 即可；leader lock 未抢到时行为等同"调度器不启动"，无状态残留
- 迁移回滚：`alembic downgrade -1`（删除生成列与唯一索引）；迁移前先执行脏数据清理：
  `UPDATE business_strategy_run SET status='failed', error_msg='迁移前清理' WHERE status='running' AND created_at < NOW() - INTERVAL 15 MINUTE`

## 当前状态

- 2026-09-19：全部工作项完成。两轮复审各发现 1 个阻断问题（follower CRUD 不传播到 leader → leader 侧 60s 周期 resync 自愈；交易日历缓存粘性 → 仅确定性结果可缓存），均已修复并验证。
- 未验证项：MySQL GET_LOCK 选主真机路径（本机 dev 为 PostgreSQL，走了 lockless 直通）；0039 MySQL 分支 DDL；多进程并发端到端。

## 交付摘要（完成时填写）
