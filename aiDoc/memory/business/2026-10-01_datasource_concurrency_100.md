# 数据源并发上限提升至 100 + 出站调用改单源独立线程池

## 需求描述

用户要求：数据源并发上限允许 100；优化请求控制，用线程池/队列方式处理避免超出并发；不同数据源并发次数独立。

## 状态

已完成

## 涉及范围

### 后端

- `core/datasource/throttle.py`：`SourceThrottle` 新增 `executor/executor_size` 字段；新增 `get_executor(source, cfg)` —— 每源独立 `ThreadPoolExecutor`，容量=max_concurrency，配置变化时重建（旧池 `shutdown(wait=False)`），线程命名 `ds-<source>` 便于排查
- `core/datasource/gateway.py`：`call_external` 从 `asyncio.to_thread`（共享默认池，高并发下池耗尽且源间互相挤占）改为 `loop.run_in_executor(单源线程池)`；准入仍由单源信号量+最小间隔控制，超出并发的调用在信号量上排队
- `modules/datasource/services/datasource_service.py`：`_CONFIG_RULES` 的 max_concurrency 上限 20 → 100

### 前端

- `views/env-config/datasource/modules/datasource-config-drawer.vue`：max_concurrency 输入上限 64 → 100

## 约束与备注

- 并发独立本来就是设计（每源独立信号量/熔断/线程池），本次是把同步执行层也对齐到单源独立
- 实测：sina（上限 2）与 fqgate（上限 4）各 10 并发任务，max_in_flight 均未超上限，线程池按 `ds-sina`/`ds-fqgate` 隔离；容量 2→100 重建正常
- 注意 min_interval_ms 与信号量叠加：间隔越大实际在飞数越低（如 sina 200ms 间隔实测 max_in_flight=1），属预期行为

## 相关文件

- `backend/core/datasource/throttle.py`、`backend/core/datasource/gateway.py`
- `backend/modules/datasource/services/datasource_service.py`
- `frontend/src/views/env-config/datasource/modules/datasource-config-drawer.vue`
- `aiDoc/contracts/boundary.md`（数据源契约两处追加）

## 记录日期

2026-10-01
