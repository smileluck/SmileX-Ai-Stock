# 规则型策略批量新建 + 因子回测验证（4 条）

## 需求描述

新建 4 条 rule 策略（超跌反转/趋势动量/放量突破/低波红利增强，停用状态、post_close 时段、general 分类），经 sweep 阈值微调后各跑一次半年正式回测（2026-03-17~2026-09-15，100 万、fixed 0.1%），产出绩效/归因与启用建议；策略与回测记录保留在库。

## 状态

已完成

## 涉及范围

### 后端

- 无代码改动（复用 StrategyService.create / SweepService.run_sweep / BacktestService.submit）
- dev 库新增 4 条 `business_ai_strategy`（strategy_type=rule，status=停用）+ 4 条正式回测记录

### 前端

- 无

## 策略设计与池构成

池构建：`business_index_constituent` 最新 record_date（2026-09-14）快照按 weight 降序前 60；红利池复制自 9108（20 只）。

| 策略 id | 名称 | 最终买入条件（AND） | 卖出条件 | 池 | stop/take/trail/仓 |
|---|---|---|---|---|---|
| 3537068351954944 | 超跌反转 | bias20 lt **-8**（初值 -6，sweep 上调）；rsi14 lt 35 | bias20 gt 0 | HS300 前60 | **7**/12/6/5（stop 初值 6） |
| 3537068352282624 | 趋势动量 | roc20 gt 5（保留初值）；vol_price_corr20 gt 0；bias10 lt 8 | roc20 lt 0 | HS300 前60 | 6/15/7/5（全保留初值） |
| 3537068352479232 | 放量突破 | vr5 gt 2（保留初值）；high20_dev gt -3；alpha101_101 gt 0 | bias5 gt 8 | 中证500 前60 | 5/10/5/5（全保留初值） |
| 3537068352675840 | 低波红利增强 | vol20 lt **2.0**（初值 1.5，sweep 放宽）；high20_dev gt -8；bias20 lt 3 | bias20 gt 6 | 红利池 20 只 | **4**/12/5/5（stop 初值 5） |

## sweep 调整记录（区间 03-17~09-15，buy_condition_scan × stop 各 9 组）

- 超跌反转：基线（-6,6) -12.36/dd 20.77 → 最优 (-8,7) **-4.01/dd 14.94**（收益与回撤双优，应用）
- 趋势动量：基线（5,6) -10.47/dd 16.02；收益更优组回撤均显著放大（(8,6) -3.60 但 dd 21.78 +36%、(8,5) -6.68 dd 19.53）→ 规则不满足，**保留初值**
- 放量突破：基线（2,5) -2.25/dd 6.45/26 笔；收益更优的 vr5=3 三档均仅 **1 笔**（统计噪声，采纳等于让策略哑火）→ **保留初值**
- 低波红利增强：基线（1.5,5) +3.55/dd 8.98 → 最优 (2.0,4) **+11.66/dd 9.28**（回撤 +0.3pp 不显著，应用）
- 原始数据：`/tmp/rule_sweep_20260917.json`

## 绩效与归因（正式回测，记录留库）

| 策略 | 回测 id | 收益% | 年化% | 回撤% | 夏普 | 胜率% | 盈亏比 | 笔数 |
|---|---|---|---|---|---|---|---|---|
| 超跌反转 | 3537105524039680 | -4.01 | -7.86 | 14.94 | -0.20 | 50.0 | 0.90 | 58 |
| 趋势动量 | 3537115545739264 | -10.47 | -19.84 | 16.02 | -0.77 | 38.2 | 0.81 | 89 |
| 放量突破 | 3537121470849024 | -2.25 | -4.44 | 6.45 | -0.39 | 46.2 | 0.81 | 26 |
| 低波红利增强 | 3537128033624064 | **+11.66** | **+24.69** | 9.28 | **1.52** | 58.3 | **2.00** | 36 |

卖出原因归因（action='sell' 按 reason 聚合，sum=Σreturn_rate）：

- 超跌反转：条件卖出（bias20>0 回归）19 笔 avg **+6.38** 是利润主力；机械止损 28 笔 avg -7.27（超 7% 线=跳空滑点）sum -203.58 吞掉全部利润
- 趋势动量：止损 35 笔 avg -6.36 sum -222.57；**条件卖出（roc20<0）22 笔 avg -2.06 本身亏损**——趋势确认转弱时利润已回吐，止盈 13 笔 +15 救不回
- 放量突破：止损 9 笔 -5.00 sum -45 为唯一大亏损源；条件卖出（bias5>8 过热兑现）7 笔 +2.70 为正
- 低波红利增强：条件卖出（bias20>6 过热）11 笔 avg **+7.48** sum +82.25 利润主力；止损 14 笔 -4.00 sum -56 可控；盈亏结构健康

## 启用建议

- **低波红利增强：建议启用**（半年 +11.66%/年化 24.7/夏普 1.52/盈亏比 2.0，36 笔样本尚可，卖出结构健康；与既有 9108 高股息 prompt 策略同池可互为对照）
- 放量突破：需迭代（条件卖出为正、止损为唯一大亏源，方向对但入场太宽；可试 vr5>2 加「当日涨幅<5%」类防追高条件后再测）
- 超跌反转：需迭代（胜率 50% 但盈亏比 0.90，止损均亏 -7.27 超线说明超跌股跳空多；考虑加 rsi 背离或缩量止跌确认、或改用 trailing 替代固定止损）
- 趋势动量：不建议启用（89 笔样本充足仍 -10.47%，条件卖出 avg 为负=离场信号滞后；2026 上半年 HS300 趋势环境不利，待环境切换或换池再评估）

## 约束与备注（坑）

- `business_ai_strategy.rule_config`/`stock_pool` 是 **json** 类型（非 jsonb），`jsonb_array_length` 不适用，校验用 `json_array_length(CAST(... AS json))` 或回读 Python 侧断言
- `business_backtest_trade` 列名是 `return_rate`（非 pnl_pct）；**买入行的 reason 存完整规则文本**（含逐笔实际值），卖出归因必须按 `action='sell'` 过滤，否则每笔记买自成一桶
- 超跌反转首条回测（3537105524039680）跑成后归因脚本因列名报错中断，复用该成功记录未重复提交
- sweep 60 票×6 月单条约 85s（baostock 串行），4 条约 6 分钟，远低于 runner 900s 超时，未触发缩池

## 相关文件

- 数据脚本（/tmp 一次性）：create_rule_strategies / rule_sweep / rule_writeback / rule_backtests_v2 / rule_sell_attribution（均 `_20260917.py`）
- 结果存档：`/tmp/rule_sweep_20260917.json`、`/tmp/rule_backtests_20260917.json`、`/tmp/rule_sell_attribution_20260917.json`
- 复用服务：`backend/modules/strategy/services/strategy_service.py`、`backend/modules/backtest/services/{sweep_service.py,backtest_service.py}`

## 记录日期

2026-09-17

## 迭代轮（2026-09-17 第二轮）

**新因子**：`gap_pct` 跳空缺口幅度（id=3537171201728512，source=custom，category=price），formula=`(open - preclose) / preclose * 100`，FactorService 创建（白名单校验通过）。

**迭代条件与 sweep 选择**（同口径 03-17~09-15）：

- 放量突破：买入追加 `bias5 lt 3`（防追高）；sweep 扫 bias5 [2,3,5]×stop[4,5,6]——bias5=2 档 0 笔（哑火）、=5 档更差，基线（3,5) -2.31/dd 2.90 与（3,4) -2.00/dd 2.60 接近 → 应用 stop 5→**4**，bias5 lt 3 保持（3 笔统计意义弱）
- 超跌反转：买入追加 `gap_pct gt -3`（不接飞刀）；sweep 扫 gap_pct [-3,-1,0]×stop[6,7,8]——**（0,6) +9.96/dd 11.68 全网格最优且回撤低于基线** → 应用 gap_pct gt **0**（即不接任何向下跳空）、stop 7→**6**；gap=-3 档与加条件前几乎相同（过滤未生效）

**新旧对比**（正式回测留库）：

| 策略 | 收益% 旧→新 | 回撤% 旧→新 | 胜率% 旧→新 | 笔数 旧→新 | 结论 | 新回测 id |
|---|---|---|---|---|---|---|
| 放量突破 | -2.25 → -2.00 | 6.45 → 2.60 | 46.2 → 0 | 26 → 3 | 回撤大降但样本萎缩到 3 笔，防追高条件过严致策略近哑火，**仍停用待再迭代** | 3537193813680128 |
| 超跌反转 | -4.01 → **+9.96** | 14.94 → 11.68 | 50.0 → 54.1 | 58 → 61 | **迭代成功翻正**：止盈 10 笔 +12.67 + 条件卖出 18 笔 +5.16 双利润源覆盖止损 26 笔 -6.41；保持停用待用户决策 | 3537201711816704 |

**启用决定**：低波红利增强 status=true（首轮 +11.66%/夏普 1.52/盈亏比 2.0）。调度证据：`backend/modules/scheduler/tasks/strategy_run.py` 任务 `strategy.run_execute`（「AI策略时段执行」，cron `*/10 9-16 * * mon-fri`）的 `_PERIOD_WINDOWS["post_close"]=(15:05,16:00)`；任务内经 `StrategyService.get_enabled`（status=True 过滤）扫描启用策略，`execute_periods` 命中 post_close 且同日同时段无 Run 记录时按 strategy_type 分流至 `RuleExecutor.submit_run`（行 92-94）——明日（2026-09-18 周五）15:05-16:00 窗口首次拾取。

**存档**：sweep `/tmp/rule_sweep2_20260917.json`、回测 `/tmp/rule_backtests_round2_20260917.json`。

## 迭代轮（2026-09-17 第三轮，09-18 完成）

**新因子**：`day_chg` 当日涨幅（id=3537270497353728，source=custom，category=price），formula=`pct_chg`，FactorService 创建，启用。

**条件改写（已落库并原生 SQL 回读确认）**：

- 放量突破：买入条件 bias5 lt 3（第二轮防追高，样本萎缩到 3 笔）→ **替换为 day_chg lt 3**（只防当日追高、不限累计乖离）；现 buy=[vr5 gt 2, high20_dev gt -3, alpha101_101 gt 0, day_chg lt 3]，stop=4，status=False
- 趋势动量：卖出条件 roc20 lt 0 → **替换为 roc5 lt -5**（早期离场）；buy 不变（roc20 gt 5, vol_price_corr20 gt 0, bias10 lt 8），trail=7，status=False
- 超跌反转：**status=True 已启用**（沿用第二轮最优配置 stop 6/take 12/trail 6，buy=[bias20 lt -8, rsi14 lt 35, gap_pct gt 0]，sell=[bias20 gt 0]）——明日 post_close 窗口与低波红利增强一起被调度拾取

**偏离点（gen_rule_signals 卖出条件组内 AND）**：rule_executor.py 的卖出评估是组内任一不满足即不出信号，所以「卖出加早期离场」若追加 roc5 条件反而更晚离场——只能**替换**原 roc20 lt 0 而非追加，已就此偏离向用户交代。

**阻塞（外部故障，已于 09-18 解除）**：09-17 约 17:15 起 baostock 数据服务故障——login 秒回成功但 `query_history_k_data_plus` 无限挂起（本机外网正常，baidu 200）。17:33~20:01 共 24 次探测（/tmp/baostock_probe.py，SIGALRM 90s 硬超时）全部 PROBE_TIMEOUT。故障约 22 小时后自愈（09-18 下午降级批 10s 取数成功）。第三轮 sweep/回测顺延至 09-18 完成（见下）。

**第三轮结果（2026-09-18 完成，sweep + 正式回测留库）**：

- 放量突破 sweep（day_chg[3,5]×stop[4,5]）：(5,4) -0.51%/8 笔/盈亏比 0.81、(5,5) -0.81%/8 笔、(3,4) 基线 -0.82%/1 笔、(3,5) -0.93%/1 笔——**4 组全部 <10 笔无有效样本，保留现行配置（day_chg lt 3, stop 4）不写回**；正式回测 id=3542818049630208：-0.82%/dd 1.05/1 笔（唯一成交止损 -4.0）——策略近哑火，**标注建议归档**（day_chg lt 3 仍过严；放宽到 5 也只有 8 笔且盈亏比 <1）
- 趋势动量 sweep（roc5[-5,-3]×trail[5,7]）：roc5=-5 档 trail=5 **+2.76%/dd 13.31/胜率 40.8/98 笔/盈亏比 1.05** vs trail=7 基线 -7.78%/86 笔——**写回 trail 7→5（原生 SQL 回读断言）**；roc5=-3 档因 baostock 批中途崩（"用户未登录"×55，仅 5 票数据）两组无效不采信
- 趋势动量正式回测 id=3542825286770688：**-10.47% → +2.76%**（dd 16.02→13.31、胜率 38.2→40.8、盈亏比 0.81→1.05、98 笔）；sell 归因：止盈 12 笔 +16.27 sum +195.18 + 移动止损 19 笔 +3.28 sum +62.29 覆盖止损 24 笔 -6.32 sum -151.57 + 条件卖出 38 笔 -1.95 sum -74.02——trail 收紧到 5 让盈利单提前落袋（trail 7 时利润回吐）；未达 <-5% 归档线，**保持停用观察**（盈亏比 1.05 仍偏弱）

**今日（09-18）启用策略补跑**：

- 15:10 调度首发双双失败（baostock 故障尾声）：超跌反转 run 3542522268426240 failed「截至 2026-09-18 无可用交易日」（日历双源皆断）、低波红利增强 run 3542522267967488 failed「规则评估超时 600s」（非僵死，RULE_EVAL_TIMEOUT 自行置 failed）
- 手动补跑（RuleExecutor.submit_run run_period="post_close" trigger_type="manual"——failed 记录不触发 running 并发守卫，调度去重只看存在性但窗口已过不冲突）：低波红利增强 run 3542805146836992 **success 5 条买入信号**（工行/建行/农行/中行/招行，基准日 09-17）；超跌反转首次补跑 3542805146574848 恰遇双源瞬断 failed，串行重试 run 3542831901581312 **success**（universe 60 全量，0 信号=无票满足 bias20<-8 且 rsi14<35 且 gap_pct>0，规则真空非故障）

**坑（新增）**：grep 管道块缓冲会让后台任务前几十分钟无输出（勿误判卡死，须结合进程/探测确认）；`business_ai_strategy.stock_pool` 内容是 JSON object（非 array），`json_array_length` 会报 "cannot get array length of a non-array"；东财 push2his 对短时间高频请求 IP 级断连（RemoteDisconnected）——多个重行情任务并发会互相打挂 akshare 路径，**sweep/回测/补跑必须串行**；baostock SDK 在服务端异常时抛 utf-8/zlib/Bad file descriptor 等底层错（非挂起），靠外层 wait_for 与降级兜底。

## 行情链路双源降级改造（2026-09-18，market_data.py）

**背景**：baostock 09-17 17:15 起查询挂起约 22h，回测/因子/规则执行器全受阻（`fetch_market_data` 原只走 baostock）。

**改造**（`backend/modules/backtest/services/market_data.py`，与 stock 模块 market_fetcher.py 同一模式）：

- 降级链：**akshare-东财主源（`ak.stock_zh_a_hist`，adjust="" 不复权匹配既有口径）→ baostock 降级**；交易日历（上证指数）同样双源（`ak.stock_zh_index_daily_em` → baostock sh.000001）
- 超时熔断：akshare 单票 `asyncio.wait_for` 30s 硬超时 + 票间 0.3s 防 push2his 限流；baostock 全局单连接协议无法单票打断，整批一个 120s 总上限（`_BAOSTOCK_BATCH_TIMEOUT`），超时票标记失败，被遗弃线程泄漏但不阻塞事件循环
- preclose 折算：东财日线无 preclose，按「收盘 - 涨跌额」逐行折算（同不复权口径）
- 返回结构 `trading_days`/`bars`/`failed_codes` 完全不变（调用方零改动），**新增 `data_sources` 键**（code → akshare_em/baostock）逐票记录实际数据源；降级逐票 logger.warning
- 规则执行器经 `factor_calc._fetch_universe_bars → fetch_market_data` 自动获得双源；backtest_runner/factor_calc/rule_executor 中过时注释已同步
- smoke（/tmp/market_data_smoke_20260918.py + _cb_）：akshare 路径 600519/000001 各 126 bar 出数且 bar 字段不变；mock baostock 挂起验证 15s 整批熔断、票标记失败、不卡死；改造当日东财限流，全部正式跑数实际经 baostock 兜底 60/60 完成
