# 板块轮动策略分析（近期轮动/明日候选/高低切换）

## 需求描述

增加轮动策略分析，支持近期轮动板块、明日轮动板块、以及板块内部高低切换，辅助提前埋伏选股与跟随趋势。

定稿方案：独立新页 `views/ai/rotation-analysis`（菜单 8032）双轨制——左侧「规则计算的轮动指标」（三张透明表：近期轮动/明日候选/高低切换）+ 右侧「AI 轮动策略报告」（analysis 模块新增 `rotation` 类型，仅 close 时段）。**AI 只推演到板块层**（主攻/潜伏/回避 + 确认信号），个股标的由高低切换表「低位启动股」数据名单给出，AI 不点名个股。

## 状态

已完成（后端回填/同步/接口/AI 生成、前端 typecheck 均验证通过）

## 涉及范围

### 后端

- **新表 `business_board_stock_daily`**（板块成分股日快照，迁移 0030）：record_date/board_type/board_code/board_name + 成分股行情（price/change_pct/amount/turnover_rate/gain_5d/gain_10d），唯一键 (record_date, board_type, board_code, stock_code)
- **`board_fetcher.py` 扩展**：
  - `fetch_boards_constituents_batch`：push2 clist `fs=b:BKxxxx` 分页拉全成分（f12,f14,f2,f3,f6,f8 + f109/f160 近5/10日涨幅）
  - `fetch_boards_history_batch`：push2his 板块日K（secid=90.BKxxxx，klt=101）回填 `business_board_daily` 缺失日期
  - **跨源代码解析**：`business_board_daily.board_code` 跟随当日板块列表源（东财 BKxxxx / 腾讯兜底 pt0xxxxx），成分股与日K只认东财代码 → `_fetch_em_board_code_map` 按 EM 板块列表建 名→BK 映射（归一化 + 去 Ⅱ/(二级) 后缀兜底），`_resolve_em_board_code` 解析；QQ 独有板块（玉米/棉花等 ~35 个概念 + 城商行Ⅱ 等细分行业）解析失败跳过告警
  - **限流逃生**：`_em_request_with_hosts` 每请求逐域名+退避重试（clist: push2→push2delay；kline: push2his→44./12. 编号 CDN），一次性域名探测扛不住批中限流抖动
- **`rotation_service.py`**（读时算不入库，沿用连板概率模式）：
  - `sync_board_stocks`：行业全量 + 概念涨幅前30 的当日成分快照，delete-当日-再插入
  - `submit_backfill(board_type="all")`：all 时行业+概念合并为一个后台任务（单一 `_BACKFILL_LOCK`，防先后两次提交相撞）；`on_conflict_do_nothing` 只补缺失日期；**跳过当日 bar**（盘中回填是半日数据）
  - `get_overview`：近N日快照现算 阶段(启动/发酵/高潮/退潮/蓄势)/明日评分(基准50+因子)/操作建议(主攻/潜伏/回避/观察)，所有因子 None 容错（回填行无净流入）
  - `get_switch_signals`：当日涨幅榜前N板块成分股按位置分层（gain_10d 80%覆盖率优先），前/后20%分组判 高低切换/分歧/共振，附高位滞涨+低位启动各5只
- **接口** `/admin/stock/rotation/*`：GET overview/switch（stock:board:list）、POST sync_stocks/backfill（stock:board:sync）；board_type 用 Literal 校验
- **定时任务** `stock.rotation_stock_sync`（38 15 * * mon-fri，board_sync 15:31 之后）
- **analysis 模块**：`rotation` 类型（VALID_TYPE_SESSIONS 仅 close）、`_collect_rotation_data`（overview+switch+涨停统计+近24h资讯）、rotation 专属系统提示词与明日推演框架；收盘自动生成扩为 market/sector/rotation
- 菜单 8032（name=ai_rotation-analysis，sort=10）；错误码 11604 同步进行中 / 11605 回填进行中

### 前端

- `views/ai/rotation-analysis/index.vue`：左侧行业/概念 RadioGroup + 同步/回填按钮 + 三页签（近期轮动按涨幅排序、明日候选按评分 top20、高低切换 expand 展开两组个股名单）；右侧 `AnalysisReportPanel analysis-type="rotation" session="close"`
- `analysis-report-panel.vue`：rotation 摘要块（近期板块 stage chips、明日候选 action+confidence chips、切换信号列表）
- typings：`Api.StockRotation` 命名空间（BackfillBoardType 含 'all'）、`AnalysisType` 加 rotation、RotationParsedResult 并入联合
- elegant-router 四件套手改（routes.ts/imports.ts/elegant-router.d.ts/**transform.ts routeMap 易漏**）；i18n 三处同步（zh-cn/en-us/app.d.ts Schema rotation 段约 60 键）；动态 i18n 键用 `as const` 对象 + `keyof typeof`（SFC 内拿不到全局 I18nKey 类型）

## 约束与备注

- 指标口径详见 rotation_service.py docstring：阶段判定顺序 退潮>高潮>发酵>启动>蓄势；评分因子（位置百分位/排名跃升/资金连续/涨停家数/量比）；切换信号阈值（高位组-低位组≤-1pp 或 高<0低≥1）
- 回填范围 = 最新快照日的全部板块（~625 个，行业 ~80% 概念 ~27% 可按名解析到东财），并发2+0.5s 间隔约 8 分钟后台执行；重复触发只补缺口
- 成分股 gain_5d/gain_10d 依赖源字段 f109/f160，缺失时由快照按日复合自累计兜底（`_pick_position_key` 80% 覆盖率降级）
- 今日（2026-09-02）已完成 59 个交易日历史回填 + 首次成分股同步（129板块/5964股）+ rotation AI 报告生成验证

## 相关文件

- backend/modules/stock/services/rotation_service.py、endpoints/rotation.py、schemas/rotation.py
- backend/modules/stock/services/board_fetcher.py（轮动扩展段）
- backend/modules/scheduler/tasks/rotation_sync.py
- backend/modules/analysis/{schemas/analysis.py, services/analysis_executor.py, scheduler tasks/analysis_run.py}
- backend/alembic/versions/0030_rotation_analysis.py
- frontend/src/views/ai/rotation-analysis/index.vue、views/ai/components/analysis-report-panel.vue
- frontend/src/service/api/stock-rotation.ts、typings/api/stock-rotation.d.ts、typings/api/analysis.d.ts

## 记录日期

2026-09-01（需求提出），完成于 2026-09-02
