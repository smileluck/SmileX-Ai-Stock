# 数据源网关 + FQGate 接入 + 数据源管理面板

## 需求描述

东财 push2his 对本机 IP 持续封禁 + baostock 查询挂起，日线双源皆断致 3 条 rule 策略哑火。要求：

1. 接入 FQGate（本机同花顺行情网关，默认 `http://127.0.0.1:17281`，无鉴权）作为**全链路兜底源**（日线/日历 + 实时报价），未运行时自动降级跳过
2. 新增数据源管理面板：集中展示所有数据源使用情况（调用量/成功率/延迟/健康状态）
3. 统一出站限流（并发+间隔+超时+熔断），避免高频并发被封禁；面板支持手动熔断/启停

## 状态

已完成（2026-09-29）

## 涉及范围

### 后端

- 新核心层 `backend/core/datasource/`：registry（12 源静态注册表）、config（sys_config 存 `datasource.*` JSON 配置，group=network，30s 缓存 + invalidate，抄 RateLimitConfigProvider 模式）、throttle（每源信号量+最小间隔+熔断器，auto/force_open/force_closed）、gateway（`call_external`/`call_external_async` 统一入口）、stats（内存按小时聚合 + 失败事件环形缓冲）
- 新表 `sys_data_source_stat`（迁移 0042，source_key+stat_hour 唯一），调度任务 `datasource.stats_flush`（60s 刷盘 + 每日 3 点清 30 天前）
- 新适配器 `modules/stock/services/_fqgate.py`：klines 日K（数字字段编号解包，preclose 前收折算）/ 交易日历（600519 日K 推导）/ realtime 批量报价 / health / search-symbols 解析指数代码
- 降级链：market_data（东财→baostock→FQGate，日历+个股）、market_fetcher（指数实时 东财→新浪→FQGate→baostock；指数历史加 FQGate 末级）、quote_helper（新浪→FQGate）
- 全部 13 类 fetcher 接入网关（board/limit_up/stock_hot/block_trade/_baostock/financial/research/macro/news/financial_service），删除散落硬编码信号量与 sleep，补齐 5 个无超时 fetcher
- 新模块 `modules/datasource/`（/admin/datasource）：list/config/update/stats/events/fqgate/config/fqgate/test，权限 `datasource:list/config/test`，迁移 0043 菜单（系统管理目录下 manage_datasource，ID 8038-8041）
- i18n `dataSource.*` 双语言

### 前端

- `views/manage/datasource/`：源状态表（启用开关/熔断 NTag/今日用量/最近错误）、配置 Drawer、失败事件弹窗、FQGate 网关卡片（base_url 编辑 + 连通性测试）、近 7 天用量 ECharts
- `service/api/datasource.ts` + `typings/api/datasource.d.ts` + locales 三件套 + `pnpm gen-route`

## 约束与备注

- FQGate 需本机安装运行（[发行仓库](https://github.com/fqgate/FQGate-releases)）；未运行时连接被拒，降级链自动跳过
- FQGate 无独立交易日历接口 → 基准股 600519 日K 推导；指数代码格式未公开 → search-symbols 运行时解析 + 进程内缓存
- FQGate records 为嵌套数组+数字字段编号（7开/8高/9低/11收/13量/19额/10最新/6昨收/55名称/5全代码），值可能是 {"value":..}/{"type":"invalid"} 包装
- 配置写 sys_config 表（value 上限 255 字符，单源 JSON 够放）；网关配置变更后 reset_runtime 清空熔断计数
- 默认限流：eastmoney 2并发/300ms/30s、sina 2/200ms/15s、baostock 1/0ms/120s（全局单连接协议必须串行）、fqgate 4/100ms/32s（官方前端并发 4、服务端预算 30s）、ths 2/500ms/180s（板块整批多页同步函数作为单次网关调用，超时需覆盖整批）、tencent 2/500ms、新闻源 2/300ms/10s；宏观指标 akshare 实为金十源，走 jin10 key
- 熔断/禁用拒绝的调用计 `rejected_calls`，不计失败（未真正外呼）

## 相关文件

- `backend/core/datasource/{registry,config,throttle,gateway,stats}.py`
- `backend/modules/stock/services/_fqgate.py`、`market_fetcher.py`、`backend/modules/backtest/services/market_data.py`、`backend/modules/strategy/services/quote_helper.py`
- `backend/modules/datasource/`（router/endpoints/services/schemas）
- `backend/database/models/sys/data_source.py`、`backend/alembic/versions/0042_add_data_source_stat.py`、`0043_seed_datasource_menu.py`
- `backend/modules/scheduler/tasks/datasource_stats.py`
- `frontend/src/views/manage/datasource/`、`frontend/src/service/api/datasource.ts`

## 记录日期

2026-09-29
