# 策略提示词升级 + 因子接入（Part 1/2a/2c/2d/2b/3 收尾）

## 需求描述

在策略回测基线（见 `2026-09-16_strategy_backtest_baseline.md`）之后做提示词工程升级：①新建 `calc_stock_factors` 因子工具接入 LLM（agent 对话与策略执行器共用注册表）；②12 条策略提示词按既定映射做因子量化改写（保留骨架，仅增量与量化替换）+ 3 条分析提示词小幅增强；③执行器实时行情快照失败从「禁止 buy」降级为「按昨收评估并标注」；④研报掘金预置 10 只研报活跃股池破冷启动；⑤风控参数经 sweep 验证后应用（落地清单见基线报告追加小节）；⑥9107 手动真实 LLM 试跑验证链路。

## 状态

已完成

## 涉及范围

### 后端

- 新工具 `backend/modules/agent/tools/factor_tools.py`：`calc_stock_factors(codes, factor_codes=None)`，复用 `modules/factor` 计算路径（`factor_calc._fetch_universe_bars` + `formula.calc_factor_values`），默认核心子集 bias5/bias20/roc5/roc20/vr5/rsi14/vol20/alpha101_101，codes 上限 50、lookback 120（与 /calc 端点一致），返回 `{end_date, factors: {code: {name, values}}, warnings}`；工具描述写明各因子口径与阈值（bias20<-5 超跌 / >8 高位、rsi14<30 超卖、vr5>2 放量、roc20 趋势方向、vol20 波动、alpha101_101 日内强弱 ±1）
- 注册：`strategy_executor._run_llm` 与 `agent_service.run_agent_stream` 两处显式 import 均加入 `factor_tools`（共用 `_REGISTRY`，无独立白名单）
- 快照降级（`strategy_executor.py`）：快照整体失败分支从「禁止任何 buy」改为「允许按昨收出 buy 信号、reason 标注『快照缺失』」；SYSTEM_PROMPT 第 3 条同步软化（个别缺失仍禁 buy）；交易引擎 3% 参考价偏差拒单守卫不动做兜底
- 数据落库（dev 库）：12 条 `business_ai_strategy.prompt_template` 因子量化改写、3 条 `business_analysis_config.prompt_template` 单句追加（复盘=量比口径、竞价前瞻=昨日强势股 bias5 均值、轮动=主题内 roc20 分位）、9112 stock_pool 预置 10 只、6 条策略风控/仓位参数 UPDATE（清单见基线报告）

### 前端

- 无

## 提示词因子量化映射（12 条）

9101 vr5>2 核实竞价放量 + 回避 bias5>6；9102 有效超跌=bias20<-5 且 rsi14<40、回避 bias20>0 伪超跌；9103 强势=roc5>3 且 bias5∈[0,4]、回踩确认 alpha101_101 由负转正；9104 低位=roc20<10 且 high20_dev>-15、启动 vr5>1.5；9105 稳健走强=bias5∈[1,5] 且 alpha101_101>0.3 + 加「低开未破买入日平台不急卖」（基线 #5）；9106 趋势=roc20>0 且 bias10∈[0,6]、bias10>8 排除；9107 低吸 bias20<-3、回避 bias20>8、vol20 波动控制；9108 抗跌=high20_dev>-8、bias20>6 暂缓；9109 vr1>2 量能 + alpha101_101>0.5 形态 + 冷却纪律「≥4 板不追/单日最多新开 1 仓/退潮空仓」（基线 #9）；9110 roc20>5 且 vol_price_corr20>0、bias20>10 不追；9111 未兑现=roc20<8 且 bias20∈[-3,3]、回避 vr5 骤升>3 脉冲；9112 追高回避=bias20>10 或 roc10>15、低位验证=bias20<5 且 high20_dev<-10、加快照缺失按昨收条款。

## 约束与备注（坑）

- **rsi14 是 0~100 口径**：DB 公式为 `.../SUM(ABS(pct_chg),14) * 100`，工具描述一度误写 0~1，已由 smoke 实值（54.72/35.69）暴露并修正
- **因子值为最近收盘口径**：竞价/盘中场景下 vr5/alpha101_101 等为昨日值，提示词中已显式标注「昨日量能口径/盘中复核」
- prompt_template 本身不含 JSON 输出纪律段（在 SYSTEM_PROMPT），「一字不动」以全文 unified diff 验证替代
- 分析配置表实际 5 行，本次只动 3 行（market/close、market/morning、rotation/close），2 条 sector 配置未动
- 9112 冷启动只破了一半：`research.sync_reports` 采集面仍只覆盖「持仓+近 30 天信号标的」，预置股池的研报数据需采集面扩展或人工触发同步后才有
- async 会话坑沿用：UPDATE 后校验一律原生 SQL 回读，不走 identity map

## 验证证据

- 工具直调 smoke：`calc_stock_factors(['600519','000001'])` 返回 8 个默认因子真实值（end_date=2026-09-16，bias20 茅台 -2.7676 / 平安 -0.1664，rsi14 35.69/54.72，warnings 空）
- 注册表 dump：11 个工具含 calc_stock_factors（执行器与对话共用）
- 降级断言：`_build_user_prompt(realtime_quotes={})` 产出含「昨日收盘价」「快照缺失」、不含「禁止给出任何 buy 信号」；快照正常分支原文未动
- 15 条 UPDATE 逐条 diff 校验：策略 12 条必需因子 code/关键词断言全中，分析配置 3 条 diff 恰好 1 删 1 增；9112 stock_pool 回读全等
- 9107 手动试跑（trigger_type=manual）：见下方「试跑记录」

## 试跑记录

9107 核心资产价值投资手动试跑（2026-09-17，run_period=manual，trigger_type=manual，真实 LLM ReAct）：

- Run 终态 **success**，error_msg 空；parsed_signals 6 条结构合法（4 hold + 2 buy：格力电器 38.17 / 中信证券 26.31，止损目标价齐全），落库 pending 信号 2 条（hold 不落表，符合既有口径）；数据保留为正式运行数据
- **工具调用证据确凿**：ai_raw_response 命中 bias20/roc/rsi/vr5/vol20/alpha101 关键词，且数值与工具 smoke 实值逐位一致（茅台 bias20=-2.77、RSI=35.7、α=-0.76 ↔ smoke -2.7676/35.6925/-0.7629），证明 LLM 实际调用了 calc_stock_factors 并按 9107 新提示词的 bias20<-3 低吸窗口选股
- 本次快照获取成功（buy_price 锚定实时快照价），快照降级条款未被触发，属预期

## 备份文件

- `/tmp/prompts_backup_20260917.sql`：两表全行 INSERT（12 策略 + 5 分析配置）
- `/tmp/params_backup_20260917.sql`：12 策略风控/仓位参数 UPDATE 快照
- `/tmp/sweep_results_20260917.json`：5 策略 sweep 原始结果
- 注意 /tmp 重启即失，如需长期保留应移入仓库或对象存储

## 相关文件

- `backend/modules/agent/tools/factor_tools.py`、`backend/modules/agent/services/tool_registry.py`
- `backend/modules/strategy/services/strategy_executor.py`、`backend/modules/agent/services/agent_service.py`
- `backend/modules/factor/services/{factor_calc.py,formula.py}`（复用路径）
- 基线报告：`aiDoc/memory/business/2026-09-16_strategy_backtest_baseline.md`

## 记录日期

2026-09-17
