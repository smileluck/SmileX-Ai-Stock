# 轮动策略分析：补齐 AI 分析策略配置

## 需求描述

2026-09-03 用户发现轮动策略分析页的「分析策略」抽屉为空。排查确认：`business_analysis_config` 表中 market（close/morning）、sector（close/morning）均有定制策略，唯独 rotation 无记录——`AnalysisConfigService.get_effective` 无记录时返回默认值（prompt 为空、明日研判开启），前端策略抽屉因此显示空白。

## 方案

以资深数据分析师视角编写 rotation（仅 close）分析策略，直接 SQL 落库（无需迁移/重启：`_analyze` 每次生成时实时读库取配置）：

- **prompt_template（主策略，599 字符）**：【角色定位】专注板块轮动的买方策略分析师，「主题-阶段-位置」三维框架 + 【分析纪律】7 条：
  1. 独立判断优先——stage/action/tomorrow_score 是规则引擎输出只作输入，与 AI 判断冲突须点出分歧，禁止照抄
  2. 主题大于板块——多板块齐动（rising_ratio_3d 高）+低位（avg_position_pct 低）+净流入占比高才是集结信号，成员<3 降权
  3. 位置决定打法——低位潜伏/中位跟随/高位只讲兑现回避
  4. 涨停梯队验证阶段——发酵扩张/高潮冲顶/退潮断板，与涨幅榜背离以涨停为准
  5. 切换信号看结构——switching/resonance/split 各自的资金含义
  6. 消息面印证——有催化+低位+流入的集结主题为埋伏首选，高位利好冲高+流出=兑现诱多
  7. 表述规范——「主线-潜伏-退潮」结构划分
- **tomorrow_prompt_template（明日推演框架，368 字符）**：主攻/潜伏双档候选（各 2-3 板块+竞价确认信号）→ 产业链联动推演（主链启动→中下游低位补涨）→ 每候选主观概率（与 tomorrow_score 相悖须说明）→ 回避清单 → 作废条件
- include_tomorrow = true

## 验证

落库后查询：rotation/close prompt_len=599、tomorrow_len=368，四类型五条配置齐全。下次手动生成或 16:05 定时任务即生效（配置读时取，不依赖重启）。

## 约束与备注

- 策略风格对齐 market/sector 既有配置（【角色定位】+【分析纪律】/【研判框架】编号条目式），便于用户在同一抽屉内统一维护
- 策略引用的字段（stage/action/tomorrow_score/rising_ratio_3d/avg_position_pct/position_pct/switching/resonance/split/gathering 等）均与 `_collect_rotation_data` 实际注入数据及 `_ROTATION_SYSTEM_PROMPT` 字段口径一一对应，无虚构字段

## 相关文件

- 落库目标：`business_analysis_config`（analysis_type='rotation', session='close'）
- backend/modules/analysis/services/analysis_executor.py（`_build_user_prompt` 配置拼接：主策略附加为「分析策略要求（用户定制）」、明日策略优先级高于内置 `_ROTATION_TOMORROW_SECTION`）
- backend/modules/analysis/services/analysis_config_service.py（get_effective 无记录回退默认）

## 记录日期

2026-09-03
