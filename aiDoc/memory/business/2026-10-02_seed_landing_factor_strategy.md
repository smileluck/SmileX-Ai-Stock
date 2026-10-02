# 因子/策略等落地种子数据库（迁移 0053-0055）

## 需求描述

「将因子和策略等都落地到种子数据库中，并检查还有那些适合落地的」。
背景：2026-10-01 的因子/策略大扩展（54 条 preset 因子 + 18 条 rule 策略）由 /tmp 临时脚本
直接灌库（new_factors.sql / gen_strategies.py），未进任何迁移——新环境 `alembic upgrade head`
后将缺失这批数据；5 条调优分析 prompt 也仅存运行库；sys_skill 空表；164 条菜单中 53 条
未授权给管理员角色（0005 起「仅插菜单不分配角色」约定累积的缺口）。

## 状态

已完成（2026-10-02，三个迁移均已升级验证 + 临时库全量验证）

## 落地内容

### 迁移 0053（核心：因子+策略）

- **56 条预置因子**（ID 段 2942406616009301-9356）：54 条 10-01 扩展因子（反转/量价/波动/
  流动性/趋势，源=运行库逐条导出，与 /tmp/new_factors.sql 完全一致）+ `day_chg`/`gap_pct`
  两条 custom 转 preset（被 5 条预置策略引用，保证种子自包含）
- **18 条预置 rule 策略**（ID 段 2942406616009401-9418，is_preset=True）：14 条 10-01 新增 +
  4 条 09-17 手工（超跌反转/趋势动量/放量突破/低波红利增强）；status 镜像回测结论
  （8 启用/10 停用）；股票池冻结 2026-10-01 沪深300/中证500 权重前 60 快照（红利池 20 只）
- **rule_config factor_id 迁移内按 code 实时解析**（SELECT 库存量 + 本迁移固定 ID 合并映射），
  查不到即 raise 回滚——杜绝静默错链；downgrade 按 ID 段 DELETE AND is_preset/source 限定

### 迁移 0054（分析配置 prompt 种子化）

5 条 (analysis_type × session)：rotation/close、market/close+morning、sector/close+morning，
含 prompt_template 与 tomorrow_prompt_template 全文（ID 段 9501-9505）；替代硬编码连接串的
一次性脚本 `scripts/seed_analysis_strategy.py`（脚本保留不再是唯一来源）；rotation/morning
原本就无记录，维持不造数据

### 迁移 0055（预置技能 + 菜单授权补齐）

- sys_skill 预置 3 条（data_citation 数据引用规范 / risk_disclaimer 风险提示 /
  a_share_conventions A股口径备忘，ID 段 9601-9603），**默认停用**不改变现有 Agent 行为
- 菜单授权补齐：动态 INSERT SELECT 把 sys_menu 全部未授权菜单授给管理员角色
  （0002 的 ADMIN_ROLE_ID=2874692539129900，permission='read' 沿用 0002 口径，
  ON CONFLICT DO NOTHING 天然幂等）；downgrade 对授权刻意 no-op（防把角色锁回旧菜单集）

## 验证结论

- 当前环境 upgrade：0053/0054 严格 no-op（因子 73/策略 31/配置 5 前后不变），0055 生效
  （技能 0→3、授权 111→164、未授权 53→0）
- 临时库 smilex_seed_test 从零 upgrade：73 preset 因子、30 策略（12 prompt + 18 rule 预置、
  8 启用）、5 配置、3 技能停用、授权 164/164，**孤儿引用 0**；downgrade 0052→re-upgrade
  往返状态完全一致
- 内容级校验：5 条 prompt 与运行库逐字节一致；18 条策略买卖条件 code 级对齐（种子库 vs 手工库）；
  56 条因子公式逐条一致

## 约束与备注

- 已知差异（有意不改写用户数据）：当前环境 18 条策略保持 is_preset=f、day_chg/gap_pct 保持
  source=custom；仅新环境生效为 preset（preset 禁删保护）
- 菜单授权是迁移执行时快照，之后运行时新增菜单（如调度动态菜单）仍需手动授权
- 「AI每日推荐」策略无需种子：recommend 调度任务按名称自动创建
- sys_config datasource.* 默认值**评估后不落地**：落库后代码默认值更新会被 DB 旧值覆盖（反向耦合）
- ID 台账：因子 0034 用 …9201-917 / 本批 …9301-9356；策略 0016/0027 用 …9101-912 /
  本批 …9401-9418；分析配置 …9501-9505；技能 …9601-9603

## 相关文件

- `backend/alembic/versions/0053_seed_factor_strategy_expansion.py`（785 行，含全量数据）
- `backend/alembic/versions/0054_seed_analysis_config.py`
- `backend/alembic/versions/0055_seed_skill_and_menu_grant.py`
- 关联记忆：[2026-10-01 因子与策略大规模扩展](./2026-10-01_factor_strategy_expansion.md)、
  [2026-09-17 规则型策略批量新建](./2026-09-17_rule_strategies_backtest.md)

## 记录日期

2026-10-02
