<!-- last-updated: 2026-09-15 -->
# 项目记忆索引

本文件是 `aiDoc/memory/` 的总入口。

## 长期记忆

暂无。

## 业务需求记忆

详细索引见 [business/README.md](./business/README.md)。近期：

- [2026-09-14 热门个股记录炸板股（涨停后破板）](./business/2026-09-14_limit_up_broken_pool.md) — 涨停池表加 `pool_type` 判别列（迁移 0032）+ 东财炸板池 `stock_zt_pool_zbgc_em` 双池同抓；`/list` 加 pool_type 筛选、stats 加 broken_count（涨停口径不变仅封板股）；前端加池类型筛选/状态列/炸板家数
- [2026-09-11 报告英文残留根治（sanitize 双 bug + 历史修复）](./business/2026-09-11_report_english_residual_fix.md) — think 块致 json 保护失效 + `\b` 边界对中英粘连失效；修复为剥 think + ASCII 环视边界 + 字段名映射扩充；修复脚本恢复 14 个历史 run 枚举码（JSONB 须 deepcopy 重赋值）
- [2026-09-09 长期资讯采集标记 + AI 分析加权](./business/2026-09-09_news_long_term_tagging.md) — 新增 news_tagger 关键词打标（标签复用轮动主题口径）+ `business_news.long_term_tags`（迁移0031）+ 存量回填；分析侧 `_collect_long_term_news` 按标签分组独立成段注入四类分析，中线背景权重 + 共振点明传导链
- [2026-09-08 策略分析偶发失败修复（think 块干扰 JSON 解析）](./business/2026-09-08_strategy_think_block_parse_fix.md) — MiniMax-M3 思考模型的英文 `<think>` 块含方括号致信号 JSON 截取解析失败（随机命中策略）；修复=解析前剥 think 块 + 原文独立落库 + 失败重试一次
- [2026-09-08 分析报告中文统一 + 轮动策略热度/趋势权重](./business/2026-09-08_report_chinese_unify_and_rotation_heat_trend.md) — 报告英文根因=轮动 prompt/注入数据的英文枚举码被 LLM 带入正文：7 类 prompt 统一追加 `_CHINESE_OUTPUT_RULE` 强约束 + 落库前 `_sanitize_report_language` 兜底替换（跳过 ```json 块保前端配色）；轮动评分新增换手率倍数/板块宽度/资金趋势/动量加速度 4 因子（存量数据，无迁移，须重启生效）
- [2026-09-03 机器人主题关键词补全（轮动主题聚合覆盖缺口）](./business/2026-09-03_robot_theme_keyword_expansion.md) — 机器人产业链板块漏网（空心杯电机/工业自动化/自动化设备 theme=None 不参与热度）→ 关键词 6→10（+空心杯电机/丝杠/自动化设备/工业自动化，精确词保互斥不吸轮毂轮边电机）；刻意不收裸"电机"/"传感器"（跨链噪声）；不拆子主题是设计取舍（gathering 集结信号需成员基数）；验证：926 板块新旧映射对比 7→10 无抢板
- [2026-09-03 轮动策略分析：补齐 AI 分析策略配置](./business/2026-09-03_rotation_analysis_strategy_config.md) — rotation 在 business_analysis_config 无记录（market/sector 均有）致策略抽屉空白；以买方轮动策略分析师视角写主策略（主题-阶段-位置三维+7 条纪律：规则输出只作输入禁照抄/集结信号三要素/位置定打法/涨停验证阶段/切换结构/消息印证/表述规范）+明日推演框架（主攻潜伏双档+产业链联动+概率+回避清单+作废条件），SQL 直接入库即生效（配置读时取，无需重启）
- [2026-09-03 分析报告排版优化（共享面板+财报页）](./business/2026-09-03_analysis_report_layout_optimize.md) — 纯视觉重构：4 共享组件（analysis-markdown/status-view/section 竖条标题/summary-card）+ utils `renderAnalysisMarkdown` 去 3 份重复；报告改摘要卡+区块标题+研判主色条、策略抽屉分组+show-count；财报页同套接入；坑：重写丢「轮动总结/总评」label 靠视觉走查补回、app.d.ts 0024 批 14 键漏同步致 typecheck 基线虚高（39→24）
- [2026-09-02 轮动策略优化：主题级聚合+评分重写（军工轮动漏判修复）](./business/2026-09-02_rotation_strategy_optimize.md) — 单板块独立评分看不见主题级资金集结 → THEME_GROUPS 18 主题关键词互斥映射，行业+概念合并聚合 heat/status（gathering 集结升温=埋伏首选）；评分改 rank_pct 分位数 + gathering 成员加分/hot 中高位减分 + 双噪音抑制；overview 契约加 themes[] 与 theme/position_pct，AI prompt 加 theme_heat；坑：算法读时算但服务须重启才生效
- [2026-09-01 板块轮动策略分析（近期轮动/明日候选/高低切换）](./business/2026-09-01_rotation_strategy_analysis.md) — 新页 rotation-analysis（菜单8032）双轨制：规则指标（阶段/评分/操作建议/高低切换信号，读时算不入库）+ AI rotation 报告类型（仅 close，板块层推演不点名个股）；新表 business_board_stock_daily（迁移0030）+ push2his 板块日K回填（board_type=all 合并单任务单锁）；坑：board_code 跨源（东财BK/腾讯pt0）须按板块名解析东财代码、push2/push2his IP 级限流须每请求逐域名降级重试、回填跳过当日半日 bar、elegant-router transform.ts routeMap 易漏
- [2026-08-31 行业板块滚动修复 + 领涨股前三名 + 热门个股连板概率](./business/2026-08-31_board_top3_leading_stocks_limitup_prob.md) — 行业板块页 flex-height 滚动修复；`business_board_daily` 加 `leading_stocks` JSON（迁移 0028），东财源按板块补抓成分涨幅前三（push2 clist，域名降级链 push2→push2delay）；热门个股连板概率=启发式评分（连板高度/封成比/炸板/首封/换手，读时算不入库）
- [2026-08-29 每日资讯分析+宏观指数+财报解读](./business/2026-08-29_news_analysis_macro_financial.md) — analysis 加 news 类型（morning/weekly，宏观/行业与个股各≤10条）+ 新模块 macro（中美 CPI/PPI/M1/M2，akshare→upsert，注入大盘/资讯分析）与 financial（新浪财务指标→AI 解读预测，持仓+信号标的定时自动）；迁移 0026 三新表+三菜单；坑：MappedAsDataclass 字段顺序（无默认在前）、APScheduler 星期写 `sun`
- [2026-08-29 动态止盈：回撤止盈 + AI 复核兜底](./business/2026-08-29_trailing_stop_take_profit.md) — 持仓峰值回撤超策略阈值（trailing_drawdown_pct，建仓快照）且仍浮盈→trailing_stop 平仓；回撤达半阈值触发 AI review 复核兜底；迁移 0025 加三列（存量持仓回填峰值/快照）
- [2026-08-28 持仓跟踪筛选/排序/滚动改造 + 亏损归因](./business/2026-08-28_position_tracking_filters_and_loss_diagnosis.md) — 持仓 Tab 滚动修复 + 策略/时间段筛选 + 服务端盈亏排序；亏损根因分析：执行价格实时无延迟，嫌疑主因=信号生成读昨日收盘快照 + T+1 当日不可止损
- [2026-08-19 AI分析目录新增大盘/板块分析菜单](./business/2026-08-19_market_sector_analysis_menu.md) — 新模块 `modules/analysis/`（/admin/analysis）+ 新表 `business_analysis_run`：大盘/板块 AI 分析落库型异步生成（三态 status + 并发守卫 11603），数据注入 prompt 单轮生成（场景 TREND_PREDICTION，不走 ReAct）；定时任务 `analysis.auto_generate` 16:05 收盘数据同步后自动生成（同日去重）；菜单 8012/8013 挂 AI 目录（name 须与 elegant-router 逐字一致），BUTTON 权限共享 `analysis:list`/`analysis:run`；前端两页面 + 共用报告面板组件（轮询+markdown 渲染+历史抽屉）；**0022 追加分析策略配置+明日研判**：`business_analysis_config`（策略提示词+明日研判开关），策略按钮在历史记录旁，研判数据增强（上证近10日/近3日行业榜对比）；坑：可空 data 接口 response_model 须 `ResponseModel[X | None]`
- [2026-08-18 策略执行异步化 + 每分钟模拟交易引擎](./business/2026-08-18_strategy_async_run_and_trade_engine.md) — 修手动执行超时：`/run` 改异步提交（running 记录落库即返回，LLM 后台分析 + 600s 兜底 + 僵死恢复）；分析只产出待执行信号（新表 business_strategy_signal），新任务 `strategy.trade_engine` 每分钟按新浪实时价执行模拟买卖 + 持仓跟踪（接管下线的 */5 position_track）；run.status bool→三态字符串（迁移 0020）
- [2026-08-17 LLM 配置增加 MiniMax + 计费模式 + 拉取模型列表](./business/2026-08-17_ai_model_minimax_billing_mode.md) — 迁移 0019 加 minimax + billing_mode（智谱两模式端点不同需区分，(provider,mode) 默认URL字典）；新端点 POST /admin/sys/ai-model/models 拉取供应商模型列表（key 必填）；前端计费模式联动 + NAutoComplete 拉取选择；坑：MappedAsDataclass 新列用 insert_default
- [2026-08-17 AI 分析预置策略 + 策略分类 + 成分股数据](./business/2026-08-17_preset_strategies.md) — 策略表加 `category`+`is_preset`；迁移 0016 预置 10 条策略（蓝筹带 30/20 固定池）；BaoStock 成分股同步 + Agent 工具 +2；**修复策略执行必挂的 4 个休眠 bug**：id 引用列 int32 溢出（0017 改 BigInteger）、ORM Enum name/value 序列化不匹配（values_callable）、CustomError(err_code=) 参数名错 13 处、异步 rollback 后属性过期 MissingGreenlet；前置：需在「LLM 配置」配默认模型
- [2026-08-16 AI 分析策略模块](./business/2026-08-16_ai_strategy_module.md) — 策略定制（提示词/股票池/执行时段）+ LLM 买卖点信号（复用 agent 模块，场景 STOCK_PICKING）+ 模拟盘自动跟踪（止损/预估卖点自动平仓）+ 回报率统计；`modules/strategy/` 4 张表 + 迁移 0015 + 前端 `views/ai/analysis/` 三 Tab；坑：app.d.ts i18n Schema 手工维护须同步
- [2026-08-16 A股数据"看似没同步"诊断与修复](./business/2026-08-16_astock_sync_diagnosis_and_fix.md) — 定时任务一直在跑；真实根因：东财 push2/push2his 按 **TLS 客户端指纹过滤**（curl 200 / Python httpx+requests 被断连，时开时关）致大盘资金流自上线 0 行 → 资金流改三级链 httpx 直连→curl_cffi(chrome 指纹)→akshare；暗盘活跃股 upsert 超 asyncpg 32767 参数上限 → `_chunked_upsert` 每批 800 行；新增 `backend/scripts/sync_astock_latest.py` 手动补拉（交易日收盘后跑，非交易日会产生伪日期戳快照）
- [2026-08-12 暗盘跟踪（大宗交易）模块](./business/2026-08-12_block_trade_module.md) — A股目录下新增「暗盘跟踪」；澄清「暗盘」=「大宗交易」（东方财富无公开「暗盘」接口，A股语境下非正式指代大宗交易/dark pool），数据源 akshare `stock_dzjy_mrtj`（每日统计）+ `stock_dzjy_hygtj`（活跃A股，4 窗口）；3 张表（daily/active/sync_log），upsert on_conflict_do_update，cron `40 15 * * mon-fri`；不纳入逐笔明细/营业部排行
- [2026-08-12 调试模式日志按天划分](./business/2026-08-12_log_rollover_midnight_fix.md) — `when='D'` 实为「启动时刻+24h」滚动且重启即重置（uvicorn reload 下永不触发），三处配置统一改 `'MIDNIGHT'` 按自然日切分；`DailyDirFileHandler` 补日期目录清理（父类认不出日期子目录，`backupCount` 此前不生效）
- [2026-08-12 股票热榜开盘时段每 5 分钟同步](./business/2026-08-12_stock_hot_5min_sync.md) — 热榜抓取 cron 改 `*/5 9-15 * * mon-fri` + 任务内交易时段守卫（9:30-11:30、13:00-15:00）；顺带修 APScheduler 星期坑（数字 `1-5`=周二至周六漏周一），三个收盘行情任务改 `mon-fri`
- [2026-08-11 A股行情同步兜底扩展](./business/2026-08-11_astock_sync_fallback_extend.md) — 东财 push2 对本机 IP 拒连致大盘/板块/热榜为空：板块加腾讯行情兜底、东财人气榜改 emappdata+新浪批量行情、指数降级链插入新浪实时层且不满 7 指数视为失败、板块入库按 board_code 同批去重；行业链后补同花顺层（含成交额/净流入，换手率仅东财有）、同日重同步先删后插防多源混杂
- [2026-08-11 A股大盘指数多源降级（akshare+Baostock+新浪）](./business/2026-08-11_astock_multi_source_fallback.md) — 大盘指数抓取三级降级链（东财→baostock→sina），历史查询不足自动回补入库；baostock 不覆盖科创50由 sina 补齐，板块/涨停池仍仅东财源
- [2026-08-10 AI 助手目录 + LLM 配置菜单调整](./business/2026-08-10_ai_assistant_menu.md) — 将「AI 配置」一级目录改名为「AI 助手」，子菜单「AI 模型配置」改名为「LLM 配置」；运行库 alembic 停在 0004 致 AI 菜单不可见，直接修复 sys_menu 数据 + 调整前端 i18n 文案；路由名 ai/ai_model 不变
- [2026-08-10 AI 模型配置功能](./business/2026-08-10_ai_model_config.md) — 新增「AI 模型配置」后台管理模块：多厂商模型 CRUD（OpenAI/Anthropic/DeepSeek/通义千问/智谱/自定义 OpenAI 兼容）+ 唯一默认模型 + 固定枚举场景绑定（智能选股/舆情分析/新闻摘要/对话问答/趋势预测）+ API Key Fernet 加密存储与脱敏显示 + httpx 连接测试（OpenAI 兼容族 Bearer token / Anthropic x-api-key）；两张新表 sys_ai_model/sys_ai_model_binding + 菜单种子迁移；前端 views/manage/ai-model 双 Tab 页面；错误码 10801-10806


- [2026-08-10 股票热榜 + 资讯菜单重组](./business/2026-08-10_stock_hot_rank.md) — 新增「资讯」一级目录，资讯聚合降为子菜单，新增「股票热榜」（东财/雪球/同花顺热榜抓取，快照入库，每日排名变化跟踪）；akshare 无同花顺热榜故自研 httpx 抓取
- [2026-08-10 股票热榜跳转与雪球/同花顺加载修复](./business/2026-08-10_stock_hot_rank_fix.md) — 雪球代码带 SH/SZ 前缀致前端拼出 `SZSH600519` 跳转 404（统一 stock_code 为纯数字）；雪球全量 5000+ 截断 Top100；同花顺原抓龙虎榜 JS 页必失败，改用富贵 hot_list JSON 接口；sync 清理当天带前缀脏数据；前端加北交所 BJ
- [2026-07-29 后端响应消息 i18n](./business/2026-07-29_backend_response_i18n.md) — 新增 `core/i18n/`（YAML key 目录 + `t()` + `Accept-Language` 解析 + 语言 ContextVar），`CustomResponseCode`/`CustomErrorCode` 的 `.msg` 按 key 懒翻译，异常类 `default_msg_key`，全量迁移约 350 条 inline 中文为 `t()`；前端 `onRequest` 注入 `Accept-Language: getLocale()`；仅 zh-CN/en-US，新增语言加 yaml 即可；日志/描述/基础设施错误不翻译
- [2026-07-28 应用用户（AppUser）后台管理](./business/2026-07-28_app_user_admin_manage.md) — AppUser 加 status/avatar/last_login_* + admin 模块 CRUD（`/admin/sys/app-user/*`）+ C 端 login/current_user 检查 status（禁用生效）+ 禁用/改密/删除复用 `OnlineUserService.kick_all_sessions` 吊销 session；前端 views/business/app-user + "业务管理"目录菜单（不分配角色）
- [2026-07-28 后端 Web 安全加固](./business/2026-07-28_security_hardening.md) — 5 项：文件上传 magic number 三方校验 + 白名单收紧；预览改 scoped token；admin/app 补 logout + 修 App session key Bug；JWT jti 黑名单；HSTS 部署 checklist
- [2026-07-27 NaiveUI 组件级主题配置](./business/2026-07-27_naiveui_component_theme_config.md) — 主题抽屉新增「组件」Tab：codegen 从 GlobalThemeOverrides 生成全部组件 × 属性表，每组件单独启用 + 表单/JSON5 混合编辑，localStorage 持久化（dev 也生效），合并优先级 用户组件配置 > 预设 > 自动；zh/en i18n

- [2026-07-23 首页仪表盘（聚合接口 + 业务统计 + 活动流）](./business/2026-07-23_homepage_dashboard.md) — 修复空白首页：新增聚合接口 `/admin/sys/dashboard/summary`（Redis 缓存 60s）+ 业务统计卡片（用户/角色/在线/今日登录）+ 最近登录时间线 + 最新公告列表；清理 5 个模板遗留组件；更新 i18n

- [2026-05-27 运维 P0 修复：健康探针 + 启动硬终止](./business/2026-05-27_ops_p0_health_probe.md) — 新增无鉴权顶级探针 `/health`（liveness）与 `/ready`（readiness，检查 DB+Redis）；`deploy.env` 健康检查从 `/openapi.json` 改为 `/ready`（修复生产环境 openapi 被禁用导致健康检查恒 404）；`main.py` lifespan 调度器同步失败改为硬阻止启动，IP 黑名单预热失败加结构化降级日志，种子数据降 WARNING；采用顶级路由方案（B 方案），澄清 `/open/*` 是商户 HMAC 签名接口，顶级路径天然不受任何业务中间件约束
- [2026-07-15 关于我们页面（前端常驻路由 + 构建时 Git 历史）](./business/2026-07-15_about_page.md) — 左右布局：左项目介绍，右 NTimeline 展示 Git 提交；about 经 `onRouteMetaGen` 标 constant 进侧边栏固定菜单（不走动态菜单）；Git 历史由自研 vite 插件构建时采集、经 virtual module 暴露，无 git 空态；纯前端不动后端
- [2026-07-14 密码复杂度策略：6-20 位且至少含字母+数字](./business/2026-07-14_password_complexity_policy.md) — 收紧 REG_PWD 用于写入侧，登录改仅非空；后端加 validator（修 new_password max 100→20）
- [2026-07-14 调度器时区修复 + create_superuser naive 时间](./business/2026-07-14_scheduler_timezone_fix.md) — APScheduler/cron 默认按服务器本地时区，UTC 服务器偏移 8h；三处显式固定 Asia/Shanghai
- [2026-07-14 用户编辑保存角色不生效修复](./business/2026-07-14_user_list_roles_for_edit.md) — 列表响应 SysUserListResponse 缺 roles，编辑抽屉无法回填 → 保存提交 role_ids:[] 清空角色；补 roles 字段（selectinload 已有，零额外查询）
- [2026-07-13 新建商户「数据校验错误」修复](./business/2026-07-13_merchant_create_validation_fix.md) — SysMerchantWithSecret.app_secret 必填导致 model_validate(ORM) 抛 ValidationError；改 default=""
- [2026-07-13 开放API测试页 crypto.subtle 报错修复](./business/2026-07-13_openapi_test_crypto_subtle_fallback.md) — HTTP/局域网下 crypto.subtle 为 undefined；新增 hmac-sha256 util（原生优先 + 纯 JS 回退）
- [2026-07-13 启动时打印日志文件落地位置](./business/2026-07-13_print_log_location_on_startup.md) — setup_logging() 动态读取文件 handler，打印日志目录/文件/归档子目录
- [2026-07-13 i18n Schema 补全 + 类型清理](./business/2026-07-13_i18n_schema_and_type_cleanup.md) — app.d.ts 补 exportTask 等；修 dict/blob/角色选择 value/number[]/bordered；typecheck 38→0
- [2026-07-13 操作日志白名单补充高频轮询接口](./business/2026-07-13_operation_log_whitelist_polling.md) — 白名单追加 route / notice-my 读；写操作与业务列表保留
- [2026-07-13 表格空字段统一显示为 "-"](./business/2026-07-13_table_empty_cell_placeholder.md) — table hook getColumns 注入默认 render，16 表自动生效；menu 手工补
- [2026-07-13 导出记录弹窗状态标识优化 + 查看全部路由修复](./business/2026-07-13_export_record_ui_and_constant_route.md) — 弹窗状态改 NTag（绿成功/红失败/黄生成中/灰排队）+ 下载按钮补 i18n 文本；export-record 纳入 constant 路由
- [2026-07-11 本地 .log 日志按日期目录滚动](./business/2026-07-11_rolling_logs_by_date.md) — Python 应用日志与 Gunicorn access/error 日志统一按 `YYYY-MM-DD/` 目录滚动
- [2026-07-05 商户管理 + 开放API HMAC 签名鉴权](./business/2026-07-05_merchant_openapi_auth.md) — sys_merchant 表 + 后台 CRUD/重置密钥 + /open/* HMAC-SHA256 签名校验 + /open/demo/ping 示例
- [2026-07-04 用户/角色管理缺陷修复 + 提交类型约束加固](./business/2026-07-04_user_role_manage_hardening.md) — 角色重名查重、create_user 加载 roles 修复 422、前端 flat-request 错误处理、User/Role 请求类型、Dict is_system 对齐、schema 校验加固
- [2026-07-07 异步导出、全局校验、角色表单与登录禁用优化](./business/2026-07-07_export_validation_login_disable.md) — 头部导出记录入口 + 操作日志异步导出 + APScheduler 定时执行/超时清理、WebSocket+轮询状态同步、全局请求参数 trim 与整数防御、角色前后端校验、禁用用户登录拦截、操作日志 total 修复

## 维护说明

- 新增记忆时，在对应目录创建 Markdown 文件，并在此索引中添加条目
- 过时的记忆应及时清理
- 记忆文件应包含日期标记，便于判断时效性
