<!-- last-updated: 2026-09-24 -->
<!-- lesson-meta: status=pending count=1 post=0 target= -->
# akshare 同步接口无超时：数据源挂住会拖死定时任务并泄漏线程

## 情境

2026-09-22 起宏观（macro.sync_all）、财报（financial.auto_interpret）、研报（research.sync_reports）定时任务连续 300s 超时；同轮排查发现轮动成分股同步（stock.rotation_stock_sync）因东财 push2 全域名对本机 IP 断连而 failed。09-22~09-23 期间源站/网络异常时 akshare 调用永久挂住，任务层面只能等 timeout 兜底。

## 坑 / 模式

- akshare 底层 requests 绝大多数接口**不传 timeout**，源站 hang（SYN 黑洞、连接建立无响应）时 `asyncio.to_thread` 里的同步调用永不返回；
- 定时任务只有整体 `asyncio.wait_for(timeout=task.timeout)`（默认 300s）：一个源挂住 = 整任务超时，其余指标全部不跑；
- `wait_for` 超时只取消 await 侧，**线程池里的线程无法取消**，会带死连接泄漏到进程结束（多次超时泄漏累积）；
- 修法：fetcher 层给每次 `to_thread` 包 `asyncio.wait_for(timeout=30)`，超时按单源失败跳过（`_AK_CALL_TIMEOUT`，见 macro/research/financial 三个 fetcher）；
- 附带环境坑：本机 Clash TUN fake-IP 模式下 DNS 全被劫持（dig 任意公共 DNS 都返回 198.18.x.x），排查"某域名断连"时先看 `ps` 有无 Clash/mihomo，再用其 controller（`/tmp/verge/verge-mihomo.sock` 的 `/dns/query`、`/rules`）确认分流与真实 IP；东财封禁表现为 TCP 通但立即 `Empty reply from server`（对 push2/push2his/编号 CDN/延时源全线生效，quote/datacenter-web/reportapi 域名不受影响，curl_cffi chrome 指纹也拒 → IP 级非 TLS 指纹过滤）；
- 板块成分股兜底源选型实测（2026-09-24）：**同花顺**详情页 `/{thshy|gn}/detail/order/desc/page/N/ajax/1/code/X/` 可用但**按请求数软限流（~5-6 页/时间窗即 302 跳登录，0.25s~1.5s 间隔无差别）**，只适合小批量/自适应熔断式兜底；**新浪** stock_sector_spot 分类体系与东财/腾讯完全不匹配（行业命中 3/124、概念 0/30）不可用；**腾讯** getRank 不支持按板块取个股。最终方案：东财降密度（并发 3/间隔 0.3s）+ EM/THS 双熔断（THS 限流错误即时熔断，当天能兜几块兜几块）+ 任务超时 900s。

## 出现次数

1（首次建档：2026-09-24 四模块采集停摆排查）

## 状态

pending

## 晋升去向

（待晋升；若再犯考虑把"外部数据源调用必须带超时"写进 modules/backend-layer-rules.md）

## 晋升后复发

0
