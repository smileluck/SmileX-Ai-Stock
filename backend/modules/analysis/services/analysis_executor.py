#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI 分析执行器 —— 大盘/板块分析（复用 agent 模块模型解析），
基于库内行情快照数据生成 markdown 分析报告 + 结构化摘要，
落库为 business_analysis_run 供前端展示与历史回看。

执行流程异步化（与策略执行器一致）：
1. submit_run 创建 running 状态执行记录后立即返回（HTTP 请求毫秒级响应）
2. LLM 分析在后台 asyncio 任务中进行（独立 session）
3. 数据直接取自库内日快照（指数/资金流/涨停统计/板块排行 + 近期趋势），不走 ReAct 工具循环，
   单轮生成更快更可控
4. 近24小时资讯以独立段注入；资讯为外部抓取内容，可能命中 LLM 输入内容审核
   （如 MiniMax 敏感词 422 拒绝整单），首次调用失败时摘除资讯段降级重试一次

分析策略可配置（business_analysis_config，每「类型×时段」一条）：
- prompt_template：分析侧重点/风格等定制要求，注入 user prompt
- include_tomorrow：报告是否包含研判章节（收盘=明日研判，早盘=今日展望，默认开启）

时段维度（session）：close-收盘分析（16:05，当日数据复盘），morning-早盘分析（9:20，
昨日收盘数据 + 近24小时资讯，侧重隔夜消息面对今日开盘的影响）。
"""
import asyncio
import json
import logging
import re
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.response.response_code import CustomErrorCode
from core.exception.errors import CustomError
from database.models.business.analysis import BusinessAnalysisRun
from database.utils.timezone import timezone
from modules.agent.services.llm_client import resolve_model, stream_chat
from modules.analysis.schemas.analysis import AnalysisConfigItem

logger = logging.getLogger(__name__)

# 后台分析整体超时（秒）：LLM 单轮流式不设总时长上限，这里兜底防止任务悬挂
ANALYSIS_TIMEOUT = 600

# 板块分析时注入 prompt 的板块数量（行业/概念各自取涨幅榜前 N）
_SECTOR_TOP_N = 15

# 大盘资金流注入 prompt 的近几日趋势
_FUND_FLOW_DAYS = 5

# 明日研判的历史数据支撑：上证指数近 N 日 / 行业板块近 N 日涨幅榜对比
_MARKET_TREND_DAYS = 10
_SECTOR_TREND_DAYS = 3
_SECTOR_TREND_TOP_N = 5

# 资讯注入：近 N 小时重点资讯条数（news.sync_all 每 5 分钟同步一次）
_NEWS_HOURS = 24
_NEWS_LIMIT = 30

# 资讯分析（news 类型）：morning 取近 24h，weekly 取近 7 天；素材条数（供 LLM 筛选到各分类 ≤10 条）
_NEWS_ANALYSIS_HOURS = 24
_NEWS_ANALYSIS_WEEKLY_HOURS = 24 * 7
_NEWS_ANALYSIS_LIMIT = 60
_NEWS_ANALYSIS_WEEKLY_LIMIT = 120

# 长期事件线索：采集时按关键词打标（news_tagger），分析注入时按标签分组独立成段
_LONG_TERM_NEWS_DAYS = 90
_LONG_TERM_NEWS_PER_TAG = 3
_LONG_TERM_NEWS_LIMIT = 20

# 后台任务强引用集合（防止 asyncio.Task 被 GC），完成后自动移除
_BACKGROUND_TASKS: set[asyncio.Task] = set()

# 输出语言强约束：_build_system_prompt 对所有报告类型统一追加，
# 防止英文枚举码/英文术语混入中文报告
_CHINESE_OUTPUT_RULE = (
    "\n语言要求（强制）：markdown 正文与 JSON 中的文本字段一律使用简体中文；"
    "阶段/状态/操作建议等术语必须写中文（如「发酵」「集结升温」「主攻」），"
    "禁止出现 ferment/gathering/attack 等英文枚举码；"
    "仅允许 PE/ROE/EPS/CPI/PPI/M1/M2 等通用金融缩写；"
    "JSON 枚举字段（stage/status/board_type 等）仅供程序解析，"
    "其英文码禁止出现在正文与文本字段中。\n"
)

# ------------------------------------------------------------------
# 系统提示词：要求 LLM 先输出 JSON 摘要（```json 代码块），再输出 markdown 报告；
# 明日研判章节按配置动态追加
# ------------------------------------------------------------------
_MARKET_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 大盘分析师，负责对A股市场当日整体表现进行点评。

我会直接提供当日真实行情数据（大盘指数、近期走势、两市资金流、涨停情绪统计），禁止凭空编造数据，分析必须基于所给数据。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "sentiment": "看多",              // 市场情绪：看多 / 中性 / 看空
  "score": 65,                     // 市场温度评分 0-100（越高越强）
  "summary": "一句话总评",          // 30 字以内
  "key_points": ["要点1", "要点2"], // 3-5 条核心观察
  "tomorrow_outlook": {            // 明日研判（未开启明日研判时省略该字段）
    "direction": "震荡偏多",        // 明日方向：看涨 / 震荡偏多 / 震荡 / 震荡偏空 / 看跌
    "summary": "一句话研判（40字内），须包含核心依据与一个可验证的确认信号"
  }
}
```
2. 再输出完整的 markdown 分析报告，结构建议：
   ## 市场概览（各指数表现点评）
   ## 消息面复盘（当日重要资讯与盘面的印证/背离，资讯与走势背离时必须点出并解释）
   ## 资金面分析（主力资金动向解读）
   ## 情绪面（涨停/连板/赚钱效应）
   ## 后市展望（机会与风险提示）

报告使用中文，条理清晰，总长度控制在 800 字以内。不构成投资建议的免责声明无需输出。
"""

_SECTOR_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 板块分析师，负责对A股行业与概念板块当日表现进行轮动解读。

我会直接提供当日真实板块行情数据（涨幅榜、成交额、主力净流入、领涨股、近期轮动对比），禁止凭空编造数据，分析必须基于所给数据。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "rotation_summary": "一句话轮动总结",   // 30 字以内
  "hot_boards": [                        // 最值得关注的 3-5 个板块
    {
      "board_name": "半导体",
      "board_type": "industry",           // industry-行业 / concept-概念
      "change_pct": 3.21,                // 涨跌幅(%)
      "viewpoint": "看好理由，40 字以内"
    }
  ],
  "key_points": ["要点1", "要点2"],       // 3-5 条核心观察
  "tomorrow_outlook": {                  // 明日研判（未开启明日研判时省略该字段）
    "direction": "轮动延续",              // 明日轮动方向：轮动延续 / 高低切换 / 热点退潮 / 新主线酝酿
    "summary": "一句话研判（40字内），须包含核心依据与一个可验证的确认信号"
  }
}
```
2. 再输出完整的 markdown 分析报告，结构建议：
   ## 行业板块表现（领涨行业解读）
   ## 概念题材动向（热点题材梳理）
   ## 消息面与板块印证（当日资讯利好/利空与板块表现的印证或背离，纯消息脉冲须标注；长期事件线索与当日板块共振时须点出传导链）
   ## 资金主线（主力净流入方向与持续性判断）
   ## 轮动展望（后市关注方向）

报告使用中文，条理清晰，总长度控制在 800 字以内。不构成投资建议的免责声明无需输出。
"""

# 明日研判章节内置框架（include_tomorrow=True 时追加到系统提示词；
# 用户未定制 tomorrow_prompt_template 时按此专业框架输出）
_MARKET_TOMORROW_SECTION = """
## 明日研判（必须包含，按专业研判框架输出）
1. **多空证据清单**：偏多、偏空证据各 2-3 条，必须引用所给数据（资金净流入延续性、量能结构、涨停家数与连板高度、指数近几日相对位置），不允许只讲单边叙事
2. **情景推演**：给出偏多/中性/偏空三个情景，每个情景写明：
   - 触发条件：明日盘中可观察的确认信号（具体到量能水平、关键点位、涨跌家数、竞价表现）
   - 概率倾向：主观概率（如 40%/35%/25%），三情景合计必须为 100%
   - 应对建议：仓位与风格取向
3. **作废条件**：明确写出 1-2 个使本研判失效的可观察信号（如放量跌破近几日低点、隔夜外盘大幅异动等，用数据可得的事实表述）
禁止"建议密切关注"式空话；每个结论必须能被明日盘面证实或证伪。
"""

_SECTOR_TOMORROW_SECTION = """
## 明日轮动研判（必须包含，按专业研判框架输出）
1. **主线阶段定位**：结合近几日涨幅榜对比（榜单延续率、新面孔占比、领涨股溢价）判断当前主线处于 发酵/高潮/分歧/退潮 哪一阶段
2. **延续性甄别**：用主力净流入连续性与成交额量级区分"有持续性的主线"与"一日游脉冲"；板块内部涨跌家数分化明显视为分歧信号
3. **情景推演**：轮动延续/高低切换/热点退潮三个情景，每个写明：
   - 触发条件：明日可观察的确认信号（竞价表现、龙头股开盘溢价、板块涨跌家数变化）
   - 概率倾向：主观概率（三情景合计 100%）
   - 应对建议：可接力方向与需回避的高位方向
4. **作废条件**：明确写出使本研判失效的可观察信号（如龙头竞价大幅低开、板块主力净流入转负）
禁止"建议关注"式空话；结论必须能被明日盘面证实或证伪。
"""

# ------------------------------------------------------------------
# 轮动策略分析（rotation，仅 close）：跨日轮动规律 + 阶段定位 + 明日埋伏推演 +
# 板块内高低切换。与 sector 的分工：sector=当日盘面点评，rotation=跨日规律与明日推演
# ------------------------------------------------------------------
_ROTATION_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 轮动策略分析师，负责对A股板块轮动规律进行跨日推演，辅助提前埋伏与趋势跟随。

我会直接提供规则引擎计算的轮动指标（板块阶段/明日候选评分/操作建议/高低切换信号）、主题热度（行业+概念板块按主题聚合，多板块同动=资金集结）、涨停情绪统计与近期资讯，禁止凭空编造数据，分析必须基于所给数据。只推演到板块层面，不点名个股、不给出具体买卖价位。

字段口径：stage-轮动阶段（start-低位启动/ferment-发酵/climax-高潮/ebb-退潮/observe-蓄势观察）；action-规则建议（attack-主攻/ambush-潜伏埋伏/avoid-回避/watch-观察）；signal-切换信号（switching-高低切换/split-分歧/resonance-共振/unknown-数据不足）；tomorrow_score-明日候选评分 0-100；theme-所属主题；position_pct-近10日涨幅位置分位（低=低位）；主题 status（gathering-集结升温/active-发酵走强/hot-高位过热/cooling-退潮/flat-平静）。

核心研判逻辑：轮动以主题为单位展开。单一板块异动可能是噪声，但同主题多板块齐动（rising_ratio_3d 高）且整体位置低（avg_position_pct 低）、资金持续净流入，就是资金集结信号——集结升温主题是提前埋伏的首选；高位过热主题的中高位成员需警惕补涨兑现。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "rotation_summary": "一句话轮动总结",     // 30 字以内
  "recent_boards": [                     // 近期轮动最值得复盘的 3-5 个板块
    {
      "board_name": "半导体",
      "board_type": "industry",
      "stage": "ferment",               // start/ferment/climax/ebb/observe
      "change_pct": 3.21,
      "viewpoint": "轮动定位与后续观察点，40 字以内"
    }
  ],
  "theme_heat": [                        // 当前主题热度观察 3-5 个（按热度/埋伏价值取舍）
    {
      "theme": "军工",
      "status": "gathering",           // gathering/active/hot/cooling/flat
      "heat": 76,
      "viewpoint": "集结/过热判断与埋伏或回避提示，40 字以内"
    }
  ],
  "tomorrow_boards": [                   // 明日轮动推演候选 3-5 个（主攻/潜伏两档为主，可含回避）
    {
      "board_name": "消费电子",
      "board_type": "industry",
      "action": "主攻",                 // 主攻 / 潜伏 / 回避
      "confidence": "中",               // 高 / 中 / 低
      "viewpoint": "推荐逻辑与确认信号，40 字以内"
    }
  ],
  "switch_signals": [                    // 板块内高低切换信号（无信号则为空数组）
    {
      "board_name": "光伏设备",
      "summary": "高位滞涨、低位补涨的判断，40 字以内"
    }
  ],
  "key_points": ["要点1", "要点2"],       // 3-5 条核心观察
  "tomorrow_outlook": {                  // 明日研判（未开启明日研判时省略该字段）
    "direction": "轮动延续",              // 轮动延续 / 高低切换 / 热点退潮 / 新主线酝酿
    "summary": "一句话研判（40字内），须包含核心依据与一个可验证的确认信号"
  }
}
```
2. 再输出完整的 markdown 分析报告，结构建议：
   ## 近期轮动复盘（主线演化路径：哪些板块接力/退潮，与规则指标印证）
   ## 主题热度与资金集结（集结升温主题为埋伏首选，高位过热主题提示兑现风险；长期事件线索影响的主题须说明持续性加成）
   ## 资金与涨停梯队（净流入连续性与连板高度对轮动阶段的验证）
   ## 板块内高低切换（规则信号解读：高位滞涨与低位启动的资金含义）
   ## 明日轮动推演（主攻/潜伏两档候选板块 + 每档的竞价确认信号）
   ## 风险提示（主线退潮/切换失败/消息面证伪的观测点）

报告使用中文，条理清晰，总长度控制在 900 字以内。不构成投资建议的免责声明无需输出。
"""

_ROTATION_TOMORROW_SECTION = """
## 明日轮动推演（必须包含，按专业研判框架输出）
1. **候选板块梯队**：给出「主攻」与「潜伏埋伏」两档候选板块（可引用规则引擎的 tomorrow_score 与 action，但须给出独立判断），每档 2-3 个板块并写明：
   - 推荐逻辑：位置高低（近10日涨幅位置）、资金连续性、涨停梯队支撑
   - 主题维度：集结升温主题的成员板块优先作为潜伏候选；高位过热主题的中高位成员规避追涨
   - 触发条件：明日竞价即可观察的确认信号（板块高开幅度、龙头竞价溢价、量能水平）
   - 概率倾向：该板块如期走强的主观概率
2. **产业链联动推演**：若上游/主链板块已启动，推演中下游低位补涨方向（如算力涨→液冷/铜连接，锂矿涨→电池/整车），写明联动传导的观察信号
3. **回避清单**：明确列出明日应回避的高位退潮方向及判定依据
4. **作废条件**：明确写出 1-2 个使本推演失效的可观察信号（如候选板块竞价集体低开、两市涨停家数骤减）
禁止"建议关注"式空话；结论必须能被明日盘面证实或证伪。
"""

# ------------------------------------------------------------------
# 早盘分析（9:20，morning）系统提示词：数据 = 昨日收盘快照 + 近24小时资讯，
# 侧重隔夜消息面对今日开盘的影响与今日观察要点
# ------------------------------------------------------------------
_MARKET_MORNING_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 大盘分析师，负责在早盘（9:20 竞价阶段）对今日A股市场进行开盘前瞻。

我会直接提供真实数据（昨日收盘指数快照与近期走势、近期资金流、昨日涨停情绪统计、近24小时重点财经资讯），禁止凭空编造数据，分析必须基于所给数据。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "sentiment": "看多",              // 今日开盘情绪预期：看多 / 中性 / 看空
  "score": 65,                     // 今日市场温度预期 0-100（越高越强）
  "summary": "一句话总评",          // 30 字以内
  "key_points": ["要点1", "要点2"], // 3-5 条核心观察
  "tomorrow_outlook": {            // 今日展望（未开启研判时省略该字段）
    "direction": "震荡偏多",        // 今日方向：看涨 / 震荡偏多 / 震荡 / 震荡偏空 / 看跌
    "summary": "一句话展望（40字内），须包含核心依据与一个可验证的确认信号"
  }
}
```
2. 再输出完整的 markdown 早盘前瞻报告，结构建议：
   ## 隔夜要闻解读（重要资讯对市场的影响研判）
   ## 昨日市场回顾（收盘数据简评）
   ## 今日开盘展望（高开/低开/平开情景推演与竞价观察信号）
   ## 今日关注要点（事件日历、量能与关键点位提示）

报告使用中文，条理清晰，总长度控制在 800 字以内。不构成投资建议的免责声明无需输出。
"""

_SECTOR_MORNING_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 板块分析师，负责在早盘（9:20 竞价阶段）对今日A股行业与概念板块进行开盘前瞻。

我会直接提供真实数据（昨日行业/概念板块涨幅榜、资金与领涨股、近几日轮动对比、近24小时重点财经资讯），禁止凭空编造数据，分析必须基于所给数据。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "rotation_summary": "一句话今日主线预期", // 30 字以内
  "hot_boards": [                        // 今日最值得关注的 3-5 个板块
    {
      "board_name": "半导体",
      "board_type": "industry",           // industry-行业 / concept-概念
      "change_pct": 3.21,                // 昨日涨跌幅(%)
      "viewpoint": "今日关注理由，40 字以内"
    }
  ],
  "key_points": ["要点1", "要点2"],       // 3-5 条核心观察
  "tomorrow_outlook": {                  // 今日展望（未开启研判时省略该字段）
    "direction": "轮动延续",              // 今日轮动方向：轮动延续 / 高低切换 / 热点退潮 / 新主线酝酿
    "summary": "一句话展望（40字内），须包含核心依据与一个可验证的确认信号"
  }
}
```
2. 再输出完整的 markdown 早盘前瞻报告，结构建议：
   ## 隔夜要闻与板块映射（资讯利好/利空哪些板块）
   ## 昨日板块轮动回顾（收盘榜单简评）
   ## 今日主线推演（延续/切换情景与竞价确认信号）
   ## 今日关注要点（可接力方向与需回避的高位方向）

报告使用中文，条理清晰，总长度控制在 800 字以内。不构成投资建议的免责声明无需输出。
"""

# 早盘"今日展望"章节内置框架（morning + include_tomorrow 时追加，对应收盘版的明日研判框架）
_MARKET_MORNING_SECTION = """
## 今日展望（必须包含，按专业研判框架输出）
1. **消息面证据清单**：隔夜资讯中偏多、偏空证据各 2-3 条，必须引用所给资讯与昨日数据，不允许只讲单边叙事
2. **开盘情景推演**：高开/平开/低开三个情景，每个情景写明：
   - 触发条件：竞价阶段可观察的确认信号（集合竞价量能、涨跌停家数、外盘与期指表现、关键指数点位）
   - 概率倾向：主观概率（如 40%/35%/25%），三情景合计必须为 100%
   - 应对建议：仓位与风格取向
3. **作废条件**：明确写出 1-2 个使本展望失效的可观察信号（如竞价放量急变、盘中突发政策消息等，用数据可得的事实表述）
禁止"建议密切关注"式空话；每个结论必须能被今日盘面证实或证伪。
"""

_SECTOR_MORNING_SECTION = """
## 今日主线推演（必须包含，按专业研判框架输出）
1. **主线阶段定位**：结合昨日涨幅榜与近几日轮动对比（榜单延续率、新面孔占比、领涨股溢价）判断当前主线处于 发酵/高潮/分歧/退潮 哪一阶段
2. **消息面映射**：逐条评估隔夜资讯利好/利空哪些昨日主线板块，区分"有消息催化的延续"与"纯情绪脉冲"
3. **情景推演**：轮动延续/高低切换/热点退潮三个情景，每个写明：
   - 触发条件：竞价阶段可观察的确认信号（板块竞价涨幅、龙头竞价溢价、涨跌停家数）
   - 概率倾向：主观概率（三情景合计 100%）
   - 应对建议：可接力方向与需回避的高位方向
4. **作废条件**：明确写出使本推演失效的可观察信号（如龙头竞价大幅低开、板块竞价集体低撤单）
禁止"建议关注"式空话；结论必须能被今日盘面证实或证伪。
"""


# ------------------------------------------------------------------
# 每日资讯分析（news 类型）：数据 = 近24h（morning）/近7天（weekly）聚合资讯 + 宏观指数，
# 输出分「宏观/行业」与「个股」两组分类要点，各不超过 10 条
# ------------------------------------------------------------------
_NEWS_MORNING_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 资讯分析师，负责在每个交易日早盘（9:20）对近24小时财经资讯进行分类解读。

我会直接提供近24小时聚合抓取的真实财经资讯列表与中美宏观指数最新读数，禁止凭空编造资讯，解读必须基于所给素材。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "macro_industry_news": [           // 宏观经济与行业资讯，最多 10 条，按影响力降序
    {
      "title": "资讯标题（可合并同类）",
      "category": "宏观政策",        // 宏观政策/央行动向/海外宏观/行业产业 之一
      "viewpoint": "核心事实与解读，60 字以内",
      "impact": "利好",              // 利好 / 利空 / 中性，并注明影响对象（如A股整体/某行业）
      "source": "财联社"
    }
  ],
  "stock_news": [                    // 个股资讯，最多 10 条，按影响力降序
    {
      "title": "资讯标题",
      "stock_name": "XX公司",        // 关联个股/公司，无法定位时写"多公司"
      "viewpoint": "核心事实与解读，60 字以内",
      "impact": "利好",              // 利好 / 利空 / 中性
      "source": "东方财富"
    }
  ],
  "summary": "一句话资讯面总评",      // 30 字以内
  "key_points": ["要点1", "要点2"]   // 3-5 条核心观察
}
```
2. 再输出完整的 markdown 资讯分析报告，结构建议：
   ## 资讯面总览（消息面整体倾向）
   ## 宏观与行业资讯解读（分类点评，与宏观指数最新读数相互印证）
   ## 个股资讯解读（重点公司事件与影响）
   ## 长期事件跟踪（长期线索的演化与受影响板块映射，无新进展简要带过）
   ## 今日观察要点（值得跟踪的发酵线索与风险提示）

筛选纪律：相似资讯必须合并为一条；与A股关联弱、纯情绪化的资讯直接忽略；两组各严格不超过 10 条。
报告使用中文，条理清晰，总长度控制在 800 字以内。不构成投资建议的免责声明无需输出。
"""

_NEWS_WEEKLY_SYSTEM_PROMPT = """你是 SmileX-AI-Stock 平台的 AI 资讯分析师，负责在周日晚对本周（近7天）财经资讯做周度复盘。

我会直接提供近7天聚合抓取的真实财经资讯列表与中美宏观指数最新读数，禁止凭空编造资讯，解读必须基于所给素材。

输出要求（严格按以下顺序，两部分缺一不可）：
1. 先输出一个 JSON 对象（包在 ```json 代码块中）：
```json
{
  "macro_industry_news": [           // 本周宏观经济与行业要闻，最多 10 条，按重要性降序
    {
      "title": "要闻标题（同类合并）",
      "category": "宏观政策",        // 宏观政策/央行动向/海外宏观/行业产业 之一
      "viewpoint": "本周核心事实与演化，80 字以内",
      "impact": "利好",              // 利好 / 利空 / 中性，并注明影响对象
      "source": "华尔街见闻"
    }
  ],
  "stock_news": [                    // 本周个股要闻，最多 10 条，按重要性降序
    {
      "title": "要闻标题",
      "stock_name": "XX公司",
      "viewpoint": "本周核心事实与演化，80 字以内",
      "impact": "利好 / 利空 / 中性",
      "source": "同花顺"
    }
  ],
  "summary": "一句话本周资讯面复盘",  // 30 字以内
  "key_points": ["要点1", "要点2"]   // 3-5 条核心观察
}
```
2. 再输出完整的 markdown 周度资讯复盘报告，结构建议：
   ## 本周资讯面复盘（消息面主线梳理）
   ## 宏观与行业要闻解读（政策与产业趋势，结合宏观指数变化）
   ## 个股要闻解读（本周重点公司事件与后续演化）
   ## 长期事件复盘（本周各长期线索的演化、板块映射与后续观察点）
   ## 下周展望（值得跟踪的线索、事件日历与风险提示）

筛选纪律：同类资讯按时间线合并为一条演化脉络；与A股关联弱的忽略；两组各严格不超过 10 条。
报告使用中文，条理清晰，总长度控制在 1000 字以内。不构成投资建议的免责声明无需输出。
"""


def _build_system_prompt(analysis_type: str, session: str, include_tomorrow: bool) -> str:
    """按分析类型/时段与配置拼装系统提示词（研判章节按需追加）"""
    if analysis_type == "news":
        # 资讯分析：morning/weekly 两套提示词，不追加研判章节（明日展望融入要点）
        return (
            (_NEWS_WEEKLY_SYSTEM_PROMPT if session == "weekly"
             else _NEWS_MORNING_SYSTEM_PROMPT) + _CHINESE_OUTPUT_RULE
        )
    if analysis_type == "market":
        if session == "morning":
            prompt, section = _MARKET_MORNING_SYSTEM_PROMPT, _MARKET_MORNING_SECTION
        else:
            prompt, section = _MARKET_SYSTEM_PROMPT, _MARKET_TOMORROW_SECTION
    elif analysis_type == "rotation":
        # 轮动策略分析仅 close 时段（VALID_TYPE_SESSIONS 约束），无 morning 变体
        prompt, section = _ROTATION_SYSTEM_PROMPT, _ROTATION_TOMORROW_SECTION
    else:
        if session == "morning":
            prompt, section = _SECTOR_MORNING_SYSTEM_PROMPT, _SECTOR_MORNING_SECTION
        else:
            prompt, section = _SECTOR_SYSTEM_PROMPT, _SECTOR_TOMORROW_SECTION
    section_title = "今日展望" if session == "morning" else "明日研判"
    if include_tomorrow:
        prompt += (
            f"\n因当前开启了「{section_title}」，报告结构中追加以下章节（放在最后，"
            "此时报告总长度可放宽至 1200 字以内）：\n" + section
        )
    else:
        prompt += (
            f"\n当前未开启「{section_title}」，报告中不要出现对{'今日' if session == 'morning' else '明日'}走势的专门预判章节，"
            "JSON 中也不要输出 tomorrow_outlook 字段。\n"
        )
    return prompt + _CHINESE_OUTPUT_RULE


def _extract_json_object(text: str) -> Optional[dict]:
    """从 LLM 回复中提取 JSON 对象（容忍 ```json 代码块 / 前后杂文），失败返回 None"""
    if not text:
        return None
    candidates = []
    # 优先取 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        candidates.append(m.group(1))
    # 否则取第一个 { 到最后一个 } 之间的内容
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


# LLM 正文兜底中文化：已知英文枚举码 → 中文术语
# （轮动 stage/action/signal、主题 status、board_type，与前端配色映射同源）
_ENUM_ZH_MAP = {
    "start": "低位启动", "ferment": "发酵", "climax": "高潮",
    "ebb": "退潮", "observe": "蓄势观察",
    "attack": "主攻", "ambush": "潜伏埋伏", "avoid": "回避", "watch": "观察",
    "switching": "高低切换", "split": "分歧", "resonance": "共振", "unknown": "数据不足",
    "gathering": "集结升温", "active": "发酵走强", "hot": "高位过热",
    "cooling": "退潮", "flat": "平静",
    "industry": "行业", "concept": "概念",
}
_ENUM_ZH_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(_ENUM_ZH_MAP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _sanitize_report_language(text: str) -> str:
    """LLM 正文兜底中文化：markdown 部分的已知英文枚举码替换为中文术语。

    开头的 ```json 代码块保持原样——枚举字段值供前端程序解析/tag 配色，
    只替换正文与文本字段中误混入的英文码。
    """
    if not text:
        return text
    m = re.match(r"\s*```(?:json)?\s*\{.*?\}\s*```", text, re.DOTALL)
    head, body = (m.group(0), text[m.end():]) if m else ("", text)
    body = _ENUM_ZH_PATTERN.sub(
        lambda mm: _ENUM_ZH_MAP[mm.group(1).lower()], body
    )
    return head + body


def _dump_rows(items: list, fields: list[str]) -> list[dict]:
    """pydantic 模型列表 → 只保留指定字段的 dict 列表（date 等转字符串）"""
    rows = []
    for it in items:
        raw = it.model_dump(mode="json")
        rows.append({k: raw.get(k) for k in fields if raw.get(k) is not None})
    return rows


async def _collect_recent_news(
    db: AsyncSession, hours: int = _NEWS_HOURS, limit: int = _NEWS_LIMIT,
) -> str:
    """近期重点资讯收集：发布时间倒序取前 N 条（标题｜源｜摘要），
    无资讯时返回空串（不阻塞分析）"""
    from datetime import timedelta

    from database.models.business.news import BusinessNews

    since = timezone.now() - timedelta(hours=hours)
    result = await db.execute(
        select(BusinessNews)
        .where(
            BusinessNews.published_at >= since,
            BusinessNews.deleted_at.is_(None),
        )
        .order_by(BusinessNews.published_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    if not rows:
        return ""
    lines = []
    for n in rows:
        ts = n.published_at.strftime("%m-%d %H:%M") if n.published_at else ""
        line = f"[{ts}] {n.title}（{n.source_name}）"
        if n.summary:
            summary = n.summary.strip()
            if summary and summary != n.title:
                line += f"：{summary[:80]}"
        lines.append(line)
    return (
        f"近 {hours} 小时重点财经资讯（共 {len(lines)} 条，先按影响力分级"
        "（宏观政策/央行动向 > 行业产业政策 > 个股与突发事件），"
        "相似资讯合并解读、与市场关联弱的忽略，评估影响时必须引用原文）：\n" + "\n".join(lines)
    )


async def _collect_long_term_news(db: AsyncSession) -> str:
    """长期事件线索收集：近 N 天带长期标签的资讯按标签分组（每组取最新 M 条），
    与当日快讯分开加权——中线背景而非当日催化。无标签资讯时返回空串（不阻塞分析）"""
    from datetime import timedelta

    from database.models.business.news import BusinessNews

    since = timezone.now() - timedelta(days=_LONG_TERM_NEWS_DAYS)
    result = await db.execute(
        select(BusinessNews)
        .where(
            BusinessNews.published_at >= since,
            BusinessNews.long_term_tags.isnot(None),
            BusinessNews.deleted_at.is_(None),
        )
        .order_by(BusinessNews.published_at.desc())
        .limit(500)
    )
    rows = result.scalars().all()
    if not rows:
        return ""

    # 按标签分组（一条多标签归入各组），每组取最新 N 条
    by_tag: dict[str, list] = {}
    for n in rows:
        for tag in n.long_term_tags or []:
            bucket = by_tag.setdefault(tag, [])
            if len(bucket) < _LONG_TERM_NEWS_PER_TAG:
                bucket.append(n)

    # 组按最新条目时间倒序，总量收敛到上限
    groups = sorted(
        by_tag.items(),
        key=lambda kv: max(
            (n.published_at for n in kv[1] if n.published_at), default=since
        ),
        reverse=True,
    )
    blocks, count = [], 0
    for tag, items in groups:
        lines = []
        for n in items:
            if count >= _LONG_TERM_NEWS_LIMIT:
                break
            ts = n.published_at.strftime("%m-%d") if n.published_at else ""
            lines.append(f"- [{ts}] {n.title}（{n.source_name}）")
            count += 1
        if lines:
            blocks.append(f"【{tag}】\n" + "\n".join(lines))
        if count >= _LONG_TERM_NEWS_LIMIT:
            break
    if not blocks:
        return ""
    return (
        f"长期事件线索（近 {_LONG_TERM_NEWS_DAYS} 天持续影响的基本面背景，"
        f"权重独立于当日快讯，按影响标签分组，共 {count} 条）：\n" + "\n\n".join(blocks)
        + "\n处理要求：作为中线背景而非当日催化；与当日盘面/板块共振时提高权重并点明传导链"
        "（如厄尔尼诺→农产品/矿产减产→农业牧渔/有色/煤/电）；事件升级或消退时标注演化方向。"
    )


# 注入 AI 分析的宏观指标（country, code）组合及展示名
_MACRO_CONTEXT_CODES = (
    ("CN", "cpi"), ("CN", "ppi"), ("CN", "m1"), ("CN", "m2"),
    ("US", "cpi"), ("US", "core_cpi"),
)
_MACRO_NAMES = {
    ("CN", "cpi"): "中国CPI同比",
    ("CN", "ppi"): "中国PPI同比",
    ("CN", "m1"): "中国M1同比",
    ("CN", "m2"): "中国M2同比",
    ("US", "cpi"): "美国CPI月率",
    ("US", "core_cpi"): "美国核心CPI月率",
}


async def _collect_macro_context(db: AsyncSession) -> str:
    """中美宏观指数最新读数收集（CPI/PPI/M1/M2），格式化为简洁文本段；
    无数据时返回空串（不阻塞分析，该段为独立注入、LLM 失败时可摘除降级）"""
    from database.models.business.macro import BusinessMacroIndicator

    parts = []
    for country, code in _MACRO_CONTEXT_CODES:
        result = await db.execute(
            select(BusinessMacroIndicator)
            .where(
                BusinessMacroIndicator.country == country,
                BusinessMacroIndicator.indicator_code == code,
                BusinessMacroIndicator.deleted_at.is_(None),
            )
            .order_by(BusinessMacroIndicator.period.desc())
            .limit(2)
        )
        rows = result.scalars().all()
        if not rows:
            continue
        name = _MACRO_NAMES.get((country, code), f"{country}-{code}")
        segs = []
        for r in rows:
            val = r.yoy if r.yoy is not None else r.value
            if val is None:
                continue
            seg = f"{r.period} {float(val):+.2f}%"
            if r.mom is not None:
                seg += f"（环比 {float(r.mom):+.2f}%）"
            segs.append(seg)
        if segs:
            parts.append(f"{name}：{'，'.join(segs)}")
    if not parts:
        return ""
    return (
        "中美宏观指数最新读数（同比，最新期在前）：\n" + "；\n".join(parts)
        + "\n（用于宏观背景判断，评估资讯与宏观环境的印证/背离）"
    )


async def _collect_news_analysis_data(db: AsyncSession, session: str) -> str:
    """资讯分析（news 类型）数据收集：morning 取近 24h，weekly 取近 7 天"""
    if session == "weekly":
        hours, limit = _NEWS_ANALYSIS_WEEKLY_HOURS, _NEWS_ANALYSIS_WEEKLY_LIMIT
        window = "本周（近 7 天）"
    else:
        hours, limit = _NEWS_ANALYSIS_HOURS, _NEWS_ANALYSIS_LIMIT
        window = "近 24 小时"
    news_prompt = ""
    try:
        news_prompt = await _collect_recent_news(db, hours=hours, limit=limit)
    except Exception:
        logger.warning("资讯分析素材获取失败", exc_info=True)

    parts = [f"当前时间：{timezone.now().strftime('%Y-%m-%d %H:%M')}"]
    if news_prompt:
        # 复用 _collect_recent_news 的分级提示文案，替换窗口描述
        news_prompt = news_prompt.replace(
            f"近 {hours} 小时重点财经资讯", f"{window}重点财经资讯", 1
        )
        parts.append(news_prompt)
    else:
        parts.append(f"{window}资讯素材：暂无数据（可能尚未同步，请在报告中注明资讯面数据缺失）")
    parts.append(
        f"请基于以上{window}真实资讯与宏观指数读数，输出 JSON 摘要与 markdown 资讯分析报告。"
    )
    return "\n\n".join(parts)


async def _collect_market_data(db: AsyncSession) -> str:
    """大盘分析数据收集：指数快照 + 上证近期走势 + 近几日资金流 + 涨停情绪"""
    from modules.stock.services.market_service import MarketService
    from modules.stock.services.limit_up_service import LimitUpService

    indices = await MarketService.get_indices(db)
    fund_flow = await MarketService.get_fund_flow(db, days=_FUND_FLOW_DAYS)
    limit_stats = await LimitUpService.get_stats(db)
    # 上证指数近期走势（支撑明日研判的趋势上下文；本地不足会自动回补）
    trend = []
    try:
        trend = await MarketService.get_history(db, "000001", _MARKET_TREND_DAYS)
    except Exception:
        logger.warning("上证指数近期走势获取失败（不影响分析）", exc_info=True)

    parts = [f"当前时间：{timezone.now().strftime('%Y-%m-%d %H:%M')}"]

    if indices:
        parts.append(
            "最新收盘大盘指数快照：\n"
            + json.dumps(
                _dump_rows(
                    indices,
                    ["index_name", "latest_price", "change_pct", "amplitude", "turnover"],
                ),
                ensure_ascii=False,
            )
        )
    else:
        parts.append("最新收盘大盘指数快照：暂无数据（可能尚未同步，请基于其他数据分析并在报告中注明）")

    if trend:
        parts.append(
            f"上证指数近 {len(trend)} 个交易日走势（研判趋势用）：\n"
            + json.dumps(
                _dump_rows(trend, ["record_date", "latest_price", "change_pct", "turnover"]),
                ensure_ascii=False,
            )
        )

    if fund_flow:
        parts.append(
            f"近 {len(fund_flow)} 日两市资金流（净流入，单位：元，负值为净流出）：\n"
            + json.dumps(
                _dump_rows(
                    fund_flow,
                    ["record_date", "main_net_inflow", "super_large_net_inflow", "small_net_inflow"],
                ),
                ensure_ascii=False,
            )
        )

    stats_raw = limit_stats.model_dump(mode="json")
    stats_fields = {
        k: stats_raw.get(k)
        for k in ("record_date", "total_count", "main_count", "chinext_count",
                  "star_count", "max_consecutive", "board_distribution")
        if stats_raw.get(k) not in (None, {}, 0)
    }
    if stats_fields:
        parts.append(f"最新涨停情绪统计：\n{json.dumps(stats_fields, ensure_ascii=False)}")

    # 资讯段由 _analyze 单独注入（LLM 内容审核失败时可整体摘除降级重试）
    parts.append("请基于以上真实数据输出 JSON 摘要与 markdown 大盘分析报告。")
    return "\n\n".join(parts)


async def _collect_sector_data(db: AsyncSession) -> str:
    """板块分析数据收集：行业/概念板块涨幅榜（含资金与领涨股）+ 近几日行业榜对比"""
    from modules.stock.services.board_service import BoardService

    parts = [f"当前时间：{timezone.now().strftime('%Y-%m-%d %H:%M')}"]

    fields = [
        "board_name", "change_pct", "turnover", "net_inflow",
        "rising_count", "falling_count",
        "leading_stock_name", "leading_stock_change_pct",
    ]
    industry_boards: list = []
    for board_type, label in (("industry", "行业"), ("concept", "概念")):
        boards = await BoardService.get_list(
            db, board_type=board_type, sort_by="change_pct", sort_order="desc"
        )
        if board_type == "industry":
            industry_boards = boards
        if boards:
            top = _dump_rows(boards[:_SECTOR_TOP_N], fields)
            parts.append(
                f"最新收盘{label}板块涨幅榜 TOP{len(top)}（change_pct-涨跌幅%，turnover-成交额，"
                f"net_inflow-主力净流入，rising/falling_count-板块内涨跌家数）：\n"
                + json.dumps(top, ensure_ascii=False)
            )
        else:
            parts.append(f"最新收盘{label}板块数据：暂无数据（可能尚未同步，请基于其他数据分析并在报告中注明）")

    # 近几日行业涨幅榜对比（支撑轮动延续性/明日研判）
    try:
        dates = await BoardService.get_dates(db, "industry")
        recent_dates = dates[:_SECTOR_TREND_DAYS] if dates else []
        trend_lines = []
        for d in recent_dates:
            day_boards = await BoardService.get_list(
                db, board_type="industry", record_date=str(d),
                sort_by="change_pct", sort_order="desc",
            )
            if day_boards:
                names = [
                    f"{b.board_name} {float(b.change_pct):+.2f}%"
                    for b in day_boards[:_SECTOR_TREND_TOP_N]
                ]
                trend_lines.append(f"{d}：{'、'.join(names)}")
        if trend_lines:
            parts.append(
                f"近 {_SECTOR_TREND_DAYS} 个交易日行业涨幅榜 TOP{_SECTOR_TREND_TOP_N} 对比（观察轮动延续性）：\n"
                + "\n".join(trend_lines)
            )
    except Exception:
        logger.warning("行业板块近期对比获取失败（不影响分析）", exc_info=True)

    # 资讯段由 _analyze 单独注入（LLM 内容审核失败时可整体摘除降级重试）
    parts.append("请基于以上真实数据输出 JSON 摘要与 markdown 板块轮动分析报告。")
    return "\n\n".join(parts)


async def _collect_rotation_data(db: AsyncSession) -> str:
    """轮动策略分析数据收集：行业+概念轮动总览（阶段/评分/建议）+ 高低切换信号 + 涨停情绪"""
    from modules.stock.services.rotation_service import RotationService
    from modules.stock.services.limit_up_service import LimitUpService

    parts = [f"当前时间：{timezone.now().strftime('%Y-%m-%d %H:%M')}"]

    overviews: dict[str, dict] = {}
    for board_type, label in (("industry", "行业"), ("concept", "概念")):
        try:
            ov = await RotationService.get_overview(db, board_type=board_type, days=10)
        except Exception:
            logger.warning("轮动总览获取失败(%s，不影响分析)", board_type, exc_info=True)
            ov = {"snapshot_date": None, "history_days": 0, "items": []}
        overviews[board_type] = ov
        items = (ov or {}).get("items") or []
        if items:
            snapshot_date = (ov or {}).get("snapshot_date")
            history_days = (ov or {}).get("history_days")
            parts.append(
                f"{label}板块轮动总览（快照日 {snapshot_date}，历史 {history_days} 个交易日，"
                f"theme-所属主题、position_pct-近10日位置分位(低=低位)，"
                f"按明日候选评分降序前 {_SECTOR_TOP_N}）：\n"
                + json.dumps(items[:_SECTOR_TOP_N], ensure_ascii=False)
            )
        else:
            parts.append(
                f"{label}板块轮动总览：暂无数据（可能尚未同步或历史不足，"
                "请基于其他数据分析并在报告中注明）"
            )

    # 主题热度（跨行业+概念关键词聚合）：单一板块异动可能是噪声，同主题多板块
    # 齐动（rising_ratio_3d 高）+ 低位（avg_position_pct 低）= 资金集结埋伏信号
    themes = ((overviews.get("industry") or {}).get("themes")
              or (overviews.get("concept") or {}).get("themes") or [])
    if themes:
        theme_slim = [
            {k: t.get(k) for k in (
                "theme", "member_count", "avg_change_pct", "avg_gain_5d",
                "rising_ratio_3d", "inflow_ratio", "avg_position_pct",
                "limit_up_total", "heat", "status",
            )}
            for t in themes[:10]
        ]
        parts.append(
            "主题热度（行业+概念板块按主题聚合：member_count-成员板块数、"
            "rising_ratio_3d-近3日成员上涨占比、inflow_ratio-今日净流入为正占比、"
            "avg_position_pct-近10日位置分位(低=低位)、heat-热度0-100、"
            "status-gathering集结升温/active发酵走强/hot高位过热/cooling退潮/flat平静，"
            "按热度降序前 10）：\n"
            + json.dumps(theme_slim, ensure_ascii=False)
        )

    # 高低切换信号（板块内部高位滞涨/低位启动的结构变化）
    for board_type, label in (("industry", "行业"), ("concept", "概念")):
        try:
            sw = await RotationService.get_switch_signals(db, board_type=board_type)
        except Exception:
            logger.warning("高低切换信号获取失败(%s，不影响分析)", board_type, exc_info=True)
            continue
        items = (sw or {}).get("items") or []
        # 只保留有意义信号（unknown 为数据不足噪音）
        meaningful = [
            it for it in items if it.get("signal") and it["signal"] != "unknown"
        ]
        if meaningful:
            slim = [
                {
                    k: it.get(k)
                    for k in ("board_name", "change_pct", "signal",
                              "high_avg_pct", "low_avg_pct")
                }
                for it in meaningful[:10]
            ]
            parts.append(
                f"{label}板块内高低切换信号（当日涨幅榜前列，signal-信号，"
                f"high/low_avg_pct-高位/低位组今日均涨幅%）：\n"
                + json.dumps(slim, ensure_ascii=False)
            )

    # 涨停情绪（连板高度是轮动阶段的核心验证）
    try:
        limit_stats = await LimitUpService.get_stats(db)
        stats_raw = limit_stats.model_dump(mode="json")
        stats_fields = {
            k: stats_raw.get(k)
            for k in ("record_date", "total_count", "main_count", "chinext_count",
                      "star_count", "max_consecutive", "board_distribution")
            if stats_raw.get(k) not in (None, {}, 0)
        }
        if stats_fields:
            parts.append(f"最新涨停情绪统计：\n{json.dumps(stats_fields, ensure_ascii=False)}")
    except Exception:
        logger.warning("涨停情绪统计获取失败（不影响分析）", exc_info=True)

    # 资讯段由 _analyze 单独注入（LLM 内容审核失败时可整体摘除降级重试）
    parts.append("请基于以上真实数据输出 JSON 摘要与 markdown 轮动策略分析报告。")
    return "\n\n".join(parts)


async def _run_llm(
    db: AsyncSession,
    analysis_type: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """单轮 LLM 调用（复用 agent 的模型解析，数据已注入 prompt，无需工具循环）"""
    from database.models.sys.ai_model import AiFunctionEnum

    resolved = await resolve_model(db, AiFunctionEnum.TREND_PREDICTION)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    final_text = ""
    async for chunk in stream_chat(resolved, messages):
        if chunk.content:
            final_text += chunk.content
    return final_text


def _build_user_prompt(
    analysis_type: str,
    data_prompt: str,
    config: AnalysisConfigItem,
) -> str:
    """数据 + 分析策略配置 → user prompt（主策略 + 明日研判策略）"""
    parts = [data_prompt]
    if config.prompt_template:
        parts.append(
            f"分析策略要求（用户定制，生成时必须遵循）：\n{config.prompt_template}"
        )
    if config.include_tomorrow and config.tomorrow_prompt_template:
        parts.append(
            "明日研判策略要求（用户定制，优先级高于默认研判框架，仅约束「明日研判」章节）：\n"
            f"{config.tomorrow_prompt_template}"
        )
    return "\n\n".join(parts)


class AnalysisExecutor:
    """AI 大盘/板块分析执行器：submit_run 落库即返回，LLM 分析在后台任务中进行"""

    @staticmethod
    async def submit_run(
        db: AsyncSession,
        analysis_type: str,
        trigger_type: str = "schedule",
        session: str = "close",
    ) -> int:
        """提交一次分析：创建 running 状态执行记录并立即返回 run_id，
        LLM 分析在后台 asyncio 任务中进行（独立 session，只传 id 不传 ORM 实例）。

        并发守卫：同类型同时段已存在 running 记录时抛 ANALYSIS_ALREADY_RUNNING。
        """
        dup = await db.execute(
            select(BusinessAnalysisRun.id).where(
                BusinessAnalysisRun.analysis_type == analysis_type,
                BusinessAnalysisRun.session == session,
                BusinessAnalysisRun.status == "running",
                BusinessAnalysisRun.deleted_at.is_(None),
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise CustomError(
                error=CustomErrorCode.ANALYSIS_ALREADY_RUNNING,
                msg="该分析正在生成中，请稍后再试",
            )

        now = timezone.now()
        run = BusinessAnalysisRun(
            analysis_type=analysis_type,
            session=session,
            run_date=now.strftime("%Y-%m-%d"),
            trigger_type=trigger_type,
            status="running",
        )
        db.add(run)
        await db.commit()  # expire_on_commit=False，flush 后 run.id 可直接取用

        task = asyncio.create_task(
            AnalysisExecutor._execute_analysis(run.id, analysis_type, session)
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        logger.info(
            "已提交 AI 分析: type=%s session=%s run_id=%s trigger=%s",
            analysis_type, session, run.id, trigger_type,
        )
        return run.id

    # ------------------------------------------------------------------
    # 后台分析
    # ------------------------------------------------------------------
    @staticmethod
    async def _execute_analysis(run_id: int, analysis_type: str, session: str = "close") -> None:
        """后台分析入口：独立 session + 整体超时兜底，任何异常都回写 Run 失败状态"""
        from database.db_manager import get_session

        async for db in get_session():
            try:
                await asyncio.wait_for(
                    AnalysisExecutor._analyze(db, run_id, analysis_type, session),
                    timeout=ANALYSIS_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001  含 TimeoutError
                if isinstance(exc, asyncio.TimeoutError):
                    err_text = f"分析执行超时（超过 {ANALYSIS_TIMEOUT} 秒）"
                else:
                    # 项目异常（CustomError 等）消息在 .msg 属性，str(exc) 可能为空
                    err_text = str(getattr(exc, "msg", None) or exc)
                logger.warning("AI 后台分析失败: run_id=%s error=%s", run_id, err_text)
                try:
                    await db.rollback()
                    await db.execute(
                        update(BusinessAnalysisRun)
                        .where(BusinessAnalysisRun.id == run_id)
                        .values(status="failed", error_msg=err_text[:1000])
                        .execution_options(synchronize_session=False)
                    )
                    await db.commit()
                except Exception:  # noqa: BLE001
                    logger.exception("回写失败分析记录异常: run_id=%s", run_id)

    @staticmethod
    async def _analyze(db: AsyncSession, run_id: int, analysis_type: str, session: str = "close") -> None:
        """分析主体：读取策略配置 -> 收集库内数据 -> LLM 生成报告 -> 解析 JSON 摘要 -> 回写成功"""
        from modules.analysis.services.analysis_config_service import AnalysisConfigService

        run_result = await db.execute(
            select(BusinessAnalysisRun).where(
                BusinessAnalysisRun.id == run_id,
                BusinessAnalysisRun.deleted_at.is_(None),
            )
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            logger.warning("分析执行记录不存在，放弃分析: run_id=%s", run_id)
            return

        # 1. 读取分析策略配置（无记录按默认：无定制提示词、明日研判开启）
        config = await AnalysisConfigService.get_effective(db, analysis_type, session)

        # 2. 收集数据（部分数据源失败不阻塞，prompt 中会注明缺失）
        if analysis_type == "news":
            data_prompt = await _collect_news_analysis_data(db, session)
        elif analysis_type == "market":
            data_prompt = await _collect_market_data(db)
        elif analysis_type == "rotation":
            data_prompt = await _collect_rotation_data(db)
        else:
            data_prompt = await _collect_sector_data(db)

        # 近24小时资讯单独收集：外部内容不可控（可能命中 LLM 内容审核导致整单失败），
        # 拼装为独立段，LLM 调用失败时可整体摘除降级重试；获取失败不阻塞。
        # news 类型资讯已在 data_prompt 内，无需重复注入
        news_prompt = ""
        if analysis_type != "news":
            try:
                news_prompt = await _collect_recent_news(db)
            except Exception:
                logger.warning("近期资讯获取失败（不影响分析）", exc_info=True)

        # 中美宏观指数读数：独立段注入（market/news），失败/无数据不阻塞，可摘除降级
        macro_prompt = ""
        if analysis_type in ("market", "news"):
            try:
                macro_prompt = await _collect_macro_context(db)
            except Exception:
                logger.warning("宏观指数读数获取失败（不影响分析）", exc_info=True)

        # 长期事件线索（厄尔尼诺/减产/关税等跨周月事件）：独立段注入，
        # 与当日快讯分开加权；同属外部内容，命中审核时可一并摘除降级
        long_term_prompt = ""
        try:
            long_term_prompt = await _collect_long_term_news(db)
        except Exception:
            logger.warning("长期事件线索获取失败（不影响分析）", exc_info=True)

        # 3. LLM 生成（系统提示词按时段/研判开关动态拼装）；
        #    资讯/宏观段放最前（行情数据 prompt 以"请基于以上真实数据输出…"收尾）
        system_prompt = _build_system_prompt(analysis_type, session, config.include_tomorrow)

        def _compose_user_prompt(with_news: bool) -> str:
            segments = []
            if with_news and news_prompt:
                segments.append(news_prompt)
            elif not with_news and news_prompt:
                segments.append(
                    "（注：近24小时资讯因故未注入，消息面数据缺失，请在报告中注明）"
                )
            if with_news and macro_prompt:
                segments.append(macro_prompt)
            if with_news and long_term_prompt:
                segments.append(long_term_prompt)
            segments.append(data_prompt)
            return _build_user_prompt(analysis_type, "\n\n".join(segments), config)

        try:
            raw_text = await _run_llm(
                db, analysis_type, system_prompt, _compose_user_prompt(True),
            )
        except Exception:
            if not news_prompt and not macro_prompt and not long_term_prompt:
                raise
            # 资讯/宏观为外部抓取内容，可能命中 LLM 输入内容审核（如 MiniMax 敏感词 422）
            # 导致整单失败；摘除外部内容段降级重试一次，保证基于行情数据的报告仍能生成
            logger.warning(
                "LLM 调用失败，摘除资讯/宏观段降级重试: run_id=%s type=%s session=%s",
                run_id, analysis_type, session, exc_info=True,
            )
            raw_text = await _run_llm(
                db, analysis_type, system_prompt, _compose_user_prompt(False),
            )
        raw_text = _sanitize_report_language(raw_text)
        run.ai_raw_response = raw_text[:20000]

        # 4. 解析 JSON 摘要（失败不影响报告本身，仅摘要为空；
        #    关闭研判时丢弃 LLM 可能误输出的 tomorrow_outlook）
        parsed = _extract_json_object(raw_text)
        if parsed is not None and not config.include_tomorrow:
            parsed.pop("tomorrow_outlook", None)
        run.parsed_result = parsed

        run.status = "success"
        await db.commit()
        logger.info(
            "AI 分析完成: type=%s session=%s run_id=%s parsed=%s tomorrow=%s",
            analysis_type, session, run_id, parsed is not None, config.include_tomorrow,
        )
