# 热门个股记录炸板股（涨停后破板）

## 需求描述

热门个股（涨停池页 `/a-stock/limit-up`）此前只记录收盘仍封板的涨停股；用户要求同时记录「涨停后又破板」的炸板股（当日触及涨停但收盘未封住）。

## 状态

已完成

## 涉及范围

### 后端

- 数据源：akshare `stock_zt_pool_zbgc_em`（东财炸板股池），新增 `limit_up_fetcher.fetch_broken_pool`；炸板池无封板资金/最后封板时间/涨停原因（置 None），连板数从「涨停统计」`days/ct` 的 ct 解析
- `business_limit_up_stock` 新增 `pool_type`（`limit_up`=收盘封板 / `broken`=炸板未封住），唯一约束扩为 `(record_date, stock_code, pool_type)`（迁移 0032，存量回填 limit_up）
- `LimitUpService.sync_all` 同时抓两池（炸板池失败仅 warning 不阻塞涨停入库），返回值加 `broken` 计数
- `GET /admin/stock/limit-up/list` 新增 `pool_type` 筛选参数（all/limit_up/broken）；`LimitUpStockItem` 加 `pool_type` 字段；炸板行跳过 `calc_continuation`（连板概率对已炸板无意义，返回 null）
- `GET /admin/stock/limit-up/stats` 新增 `broken_count`；total_count/板块分布/最高连板口径不变（仅封板股）
- 定时任务 `stock.limit_up_sync`（15:35 mon-fri）文案同步为涨停/炸板双池

### 前端

- 热门个股页筛选区新增池类型 RadioGroup（全部/封板/炸板），表格新增「状态」列（封板=红 tag / 已炸板=橙 tag），统计卡新增「炸板家数」（grid m:6→m:7）
- 类型：`Api.StockLimitUp.PoolType`（all/limit_up/broken）、item 加 `pool_type`、stats 加 `broken_count`；i18n 双语 + `app.d.ts` Schema 同步（poolAll/poolLimitUp/poolBroken/poolStatus/statusSealed/statusBroken/brokenCount）

## 约束与备注

- 东财两池天然互斥：盘中炸板又回封的只出现在涨停池，无同股同日冲突
- 炸板池接口仅支持最近 30 个交易日（akshare 抛 ValueError），只影响手动补历史，不影响每日收盘同步
- 涨停统计口径刻意不变（total_count 仅封板股），炸板家数单列，避免影响依赖涨停家数的下游（策略/轮动分析）

## 相关文件

- `backend/database/models/business/stock_market.py`（BusinessLimitUpStock）
- `backend/alembic/versions/0032_limit_up_pool_type.py`
- `backend/modules/stock/services/limit_up_fetcher.py` / `limit_up_service.py`
- `backend/modules/stock/schemas/limit_up.py` / `backend/modules/stock/endpoints/limit_up.py`
- `backend/modules/scheduler/tasks/stock_market_sync.py`
- `frontend/src/typings/api/stock-limit-up.d.ts` / `frontend/src/service/api/stock-limit-up.ts`
- `frontend/src/views/a-stock/limit-up/index.vue`
- `frontend/src/locales/langs/zh-cn.ts` / `en-us.ts` / `frontend/src/typings/app.d.ts`

## 记录日期

2026-09-14
