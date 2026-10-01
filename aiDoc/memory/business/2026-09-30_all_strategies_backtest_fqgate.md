<!-- last-updated: 2026-10-01 -->
# 启用 FQGate + 全部 16 条策略回测与优化

## 需求描述

启用 FQGate 本机网关（第三行情源），对全部策略（4 rule + 12 prompt）跑回测，并根据结果反馈优化。

## 状态

已完成（2026-10-01）：FQGate 用户确认风险声明后正常运行（凌晨 04:01 进程退出，次日重启即直接监听）；16 条策略回测与 sweep 优化全部完成。

## FQGate 启用与修复记录（2026-10-01）

- 用户确认风险声明后网关开始服务（THS 游客登录，endpoint maczhuhq1.123ths.com:9602）；进程凌晨退出属个案，重启即恢复
- **修复**：`_fqgate.py` 日 K 请求日期须为 YYYYMMDD 紧凑格式——v1.0.5「修复历史 K 线复权参数和日期范围校验」后 `YYYY-MM-DD` 返回 1003「请求内容不完整或格式不正确」（`adjust:""` 仍可正常接受）；改为 body 内 `start_date.replace("-","")`
- 修复后 `/admin/datasource/fqgate/test` 三步全通（health 37ms / daily_klines 48ms / realtime_quote 83ms），fqgate 熔断计数归零，三源（东财/baostock/FQGate）circuit 全 closed

## FQGate 安装记录（2026-09-30）

- 本机未安装 → 从官方发行仓库 [fqgate/FQGate-releases](https://github.com/fqgate/FQGate-releases) 下载 `FQGate-1.0.5-macos-arm64-ADHOC.zip`（sha256 校验一致）解压至 `~/Applications/fqgate/FQGate.app`，`xattr -dr com.apple.quarantine` 去隔离
- 后台启动进程正常，但为首启桌面应用：停在「风险声明」确认窗口，确认前不监听 17281；CLI 无跳过参数（`--help` 仅 host/port/mcp 桥接）；osascript 点击因辅助功能权限挂起不可行
- 运行日志 `~/Library/Logs/fqgate/fqgate-YYYY-MM-DD.log`

## prompt 策略回测（recorded_replay，区间 2026-08-18~09-29 = 信号覆盖窗口，100 万、fixed 0.1%）

信号覆盖：`business_strategy_signal` 列是 `run_date`（非 trade_date）、无 is_deleted；12 条 prompt 信号量 1~185 条不等，资金潜伏低吸仅 1 条（09-24）、研报掘金 7 条，样本过小仅供参考。

| 策略 | 收益% | 回撤% | 夏普 | 胜率% | 盈亏比 | 笔数 | 判定 |
|---|---|---|---|---|---|---|---|
| 涨停题材龙头打板 | **+25.32** | 6.10 | 6.11 | 72.7 | 3.93 | 11 | 最佳 |
| 高股息红利防御 | +1.85 | 2.37 | 2.06 | 58.3 | 1.76 | 24 | 稳健盈利 |
| 竞价超跌低吸 | +1.65 | 2.27 | 1.53 | 33.3 | 2.82 | 3 | 样本太小 |
| 午盘强势回踩低吸 | +0.67→**+0.96** | 4.60 | 0.64 | 46.7 | 1.14 | 15 | sweep 微调 stop 4→5 已写回 |
| 资金潜伏低吸 | -0.12 | 0.50 | -0.53 | 0 | 0 | 1 | 样本不足 |
| 研报掘金 | -0.94 | 1.50 | -3.05 | 0 | 0 | 3 | 样本不足 |
| 核心资产价值投资 | -3.33 | 4.38 | -3.00 | 18.8 | 0.33 | 16 | 信号质量问题 |
| 竞价高开抢筹 | -3.48 | 6.54 | -1.55 | 42.9 | 0.65 | 14 | 信号质量问题 |
| 大盘共振波段 | -4.41 | 5.15 | -4.20 | 20.0 | 0.11 | 10 | 信号质量问题 |
| 午盘补涨轮动 | -7.06 | 8.61 | -2.57 | 27.3 | 0.24 | 11 | 信号质量问题 |
| 尾盘趋势确认 | -9.32 | 11.97 | -2.99 | 25.0 | 0.28 | 8 | 信号质量问题 |
| 尾盘资金抢筹 | -9.57 | 9.57 | -7.28 | 0 | 0 | 7 | 信号质量问题，最差 |

## prompt sweep（27 组风控网格/条，9 条）

**核心发现：prompt 型策略对风控参数大面积不敏感**（信号自带目标价/止损价，策略级参数仅兜底——09-16 已记录的「参数组并列非 bug」在此量化证实）：竞价高开抢筹/核心资产/涨停打板/高股息/大盘共振 5 条 27 组结果完全相同。有响应的：

- 午盘强势回踩低吸：(stop5,take7,trail5) +0.96 vs 基线 +0.67，回撤同为 4.60，不劣于 → **写回 stop 4→5**，复测 id=3612465927168000 逐位一致
- 尾盘趋势确认：最优 (7,4,5) -6.12/dd 8.86（仍深亏，参数救不了信号）
- 午盘补涨轮动：最优 (3,5,3) -5.96/dd 7.24（仍亏，盈亏比反而 0.24→0.17）
- 尾盘资金抢筹：最优仍 -9.23/pf 0（无药可救的参数面）

**结论**：亏损 prompt 策略的病根在信号质量（prompt 选股），不在风控参数。建议停用：尾盘资金抢筹（胜率 0/pf 0）、尾盘趋势确认、午盘补涨轮动、大盘共振波段（均 pf<0.3）；核心资产价值投资与竞价高开抢筹胜率 <43%/pf<0.7 观察。**启用面决策留用户**。

## 4 条 rule 策略

当日早些时候已完成第四+五轮（见 2026-09-17_rule_strategies_backtest.md）：低波红利增强 +12.13/超跌反转 +8.22/趋势动量 +5.12/放量突破 +2.93，全部翻正。

## 存档

- `/tmp/prompt_backtests_20260930.json`、`/tmp/prompt_sweeps_20260930.json`

## 记录日期

2026-09-30

## 菜单调整（2026-10-01）

- 应用户要求把「数据源管理」从系统管理根层移入新建「环境配置」子目录：迁移 `0044_move_datasource_to_env_config.py`（新建 CATALOG `manage_env-config` id=2942406616008042 parent=manage、UPDATE 8038 的 parent_id），补 i18n `route.manage_env-config`（zh-cn 环境配置 / en-us Environment Config）
- **菜单 name/path/component 均未变**——dynamic 路由模式按 name 匹配组件，仅改 parent_id 即可，页面组件解析不受影响；CATALOG 行 `component` 必须为 NULL（写 layout.base 会被 elegant-router transform 嵌套双层布局），多级目录拍平为 layout.base 平级子路由，侧边栏仍按后端菜单树显示三级

## 菜单调整追加（2026-10-01 第二轮）

- 用户改要求「环境配置」放根级：迁移 `0045_move_env_config_to_root.py`（parent_id→NULL、name manage_env-config→**env-config**、path→/env-config、component NULL→**layout.base**、sort=9），i18n 键同步改 route.env-config
- **根级 CATALOG 两条硬约定**（transform.ts isFirstLevelRoute=name 不含 "_"）：name 必须无下划线（否则被当非一级路由拍平出错）、component 必须是 layout.base；子级目录则相反——component 必须为 NULL（0044 注释）

## 菜单调整追加（2026-10-01 第三轮，typecheck 修正）

- 纯 DB 目录 key 不在 I18nRouteKey（由 views 目录生成）导致 locale typecheck 报 TS2353 → 视图 `git mv views/manage/datasource → views/env-config/datasource` + `pnpm gen-route` + 迁移 `0046_rename_datasource_menu.py`（菜单 8038 改 name=env-config_datasource、path=/env-config/datasource、component=view.env-config_datasource；按钮行不动），locale key 同步改 'env-config_datasource'
- 坑：locale 对象 key 含连字符必须加引号（'env-config_datasource'），裸写 TS1005；`pnpm gen-route` 有交互提示但自动继续
