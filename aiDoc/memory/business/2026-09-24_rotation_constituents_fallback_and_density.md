# 轮动成分股同步：东财降密度 + 同花顺兜底 + 双熔断

## 需求描述

轮动板块成分股快照（stock.rotation_stock_sync → business_board_stock_daily）自 2026-09-23 起因东财 push2 全域名对本机 IP 封禁而中断。要求：① 降低东财批量抓取请求密度避免再触发封禁；② 给成分股增加非东财兜底源，摆脱单点。

## 状态

已完成（2026-09-24）

## 涉及范围

### 后端

- `modules/stock/services/board_fetcher.py`：
  - `_EM_TOP_STOCKS_CONCURRENCY` 5→3、`_EM_TOP_STOCKS_INTERVAL` 0.1→0.3（降密度防封）
  - 新增同花顺成分股兜底链：`_fetch_ths_board_code_map`（akshare 行业/概念名→88/30 代码映射，复用归一化名键）、`_fetch_ths_constituents_sync`（`/{thshy|gn}/detail/order/desc/page/N/ajax/1/code/X/` ajax 分页，20 行/页，GBK，逐请求刷新 v cookie，登录跳转/403 抛 `THSRateLimitedError`）、`_fallback_ths_constituents`（按名解析，独立信号量限速）
  - `fetch_boards_constituents_batch` 重构：东财名映射失败不再中断整批（该类型直接走同花顺）；EM 连续 3 板块失败熔断东财；THS 限流错误即时熔断同花顺（其余非限流失败连续 3 次熔断）；名称未匹配不计入限流熔断
- 任务 `stock.rotation_stock_sync` 超时 300→900s（DB 直改 sys_scheduled_task.timeout）

### 前端

无。

## 约束与备注

- **兜底源选型实测**（同日）：同花顺详情页按请求数软限流（约 5-6 页/时间窗即 302 跳登录，与间隔快慢无关）→ 只能"当天能兜几块兜几块"；新浪 stock_sector_spot 分类与东财/腾讯完全不匹配（行业命中 3/124、概念 0/30）不可用；腾讯 getRank 无按板块取个股能力
- THS 成分股无近5/10日涨跌幅列，gain_5d/gain_10d=None 由查询侧按日快照自累计兜底（沿用既有约定）
- 快照 board_code/board_name 沿用入参（business_board_daily 当日源），不产生跨源代码污染
- 东财封禁期间每日快照为部分覆盖（THS 熔断前能抓的板块数），解封后自动恢复全量
- 熔断是批次级（state dict 闭包），不跨任务持久化

## 相关文件

- backend/modules/stock/services/board_fetcher.py
- backend/modules/stock/services/rotation_service.py（未改，消费方契约不变）
- aiDoc/memory/lessons/2026-09-24-akshare-no-timeout-task-hang.md（同日上游故障排查）

## 记录日期

2026-09-24
