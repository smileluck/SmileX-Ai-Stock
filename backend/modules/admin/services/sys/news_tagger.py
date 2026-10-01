#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
长期资讯打标器（采集时调用）

部分资讯是影响持续数周/数月的长周期事件（如厄尔尼诺对农业/铜/煤/电的供给冲击），
不应与当日快讯同权重处理。本模块在资讯入库时按关键词规则打上「长期事件标签」，
标签口径复用轮动模块 THEME_GROUPS 的主题名，便于与板块轮动主题联动。

规则从简，误标/漏标后续按 badcase 补词。
"""

# (事件关键词元组, 影响标签元组)：标题命中任一关键词即打全部标签；
# 仅摘要命中时需 >=2 个关键词才打标（防误标）
_LONG_TERM_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    # 气候类：持续数月的农产品/矿产/能源供给冲击
    (("厄尔尼诺", "拉尼娜", "极端天气", "干旱", "洪涝", "洪灾", "台风", "寒潮", "霜冻"),
     ("农业牧渔", "有色贵金属", "煤炭石油", "电力公用")),
    # 有色矿产供给
    (("铜矿减产", "铜矿罢工", "铜精矿", "铝土矿", "稀土管制", "稀土出口", "锂矿减产",
      "镍矿", "锡矿", "锑矿"),
     ("有色贵金属",)),
    # 能源供给
    (("煤矿减产", "煤炭产能", "煤矿安全", "欧佩克", "OPEC", "原油减产", "石油减产",
      "天然气供应", "油气限产"),
     ("煤炭石油",)),
    # 产能/供给政策周期
    (("产能出清", "供给侧改革", "反内卷", "减产协议"),
     ("有色贵金属", "化工", "煤炭石油")),
    # 货币政策周期
    (("降息", "加息", "量化宽松", "缩表", "降准"),
     ("金融",)),
    # 贸易/地缘政策周期
    (("关税", "制裁", "出口管制", "禁运", "反倾销"),
     ("有色贵金属", "化工", "汽车")),
    # 农业周期
    (("猪周期", "生猪产能", "能繁母猪", "粮食安全", "粮食减产", "收储"),
     ("农业牧渔",)),
)


def tag_long_term(title: str | None, summary: str | None = None) -> list[str]:
    """资讯标题/摘要 → 长期事件标签列表（空 = 短期资讯）

    标题命中任一规则关键词即打标；标题未命中时，摘要需累计命中 >=2 个
    关键词才打标（摘要噪声大，防误标）。
    """
    title = (title or "").strip()
    summary = (summary or "").strip()
    if not title:
        return []

    tags: list[str] = []
    for keywords, rule_tags in _LONG_TERM_RULES:
        if any(k in title for k in keywords):
            tags.extend(rule_tags)

    if not tags and summary:
        hits = sum(
            1 for keywords, _ in _LONG_TERM_RULES for k in keywords if k in summary
        )
        if hits >= 2:
            for keywords, rule_tags in _LONG_TERM_RULES:
                if any(k in summary for k in keywords):
                    tags.extend(rule_tags)

    # 保序去重
    return list(dict.fromkeys(tags))


# ---------------------------------------------------------------------------
# 长期主线打标（事件/产业级口径，比长期事件标签更细）
# ---------------------------------------------------------------------------

# (主线名, 关键词元组, 映射的轮动主题元组)：标题命中任一关键词即打该主线；
# 仅摘要命中时需 >=2 个关键词才打标。映射主题供因子/板块联动反查。
MAINLINE_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("半导体",
     ("半导体", "芯片", "晶圆", "光刻", "EDA", "先进封装", "存储芯片", "存储器",
      "HBM", "DRAM", "NAND", "台积电", "中芯国际", "国产芯片"),
     ("半导体",)),
    ("光通信",
     ("光模块", "光通信", "CPO", "光纤", "硅光", "光器件", "光芯片", "800G", "1.6T"),
     ("通信",)),
    ("房地产",
     ("房地产", "楼市", "房贷", "保障房", "土拍", "房企", "地产债", "公积金",
      "限购", "限售"),
     ("地产基建",)),
    ("厄尔尼诺",
     ("厄尔尼诺", "拉尼娜", "极端天气", "干旱", "洪涝", "洪灾", "台风", "寒潮"),
     ("农业牧渔", "煤炭石油", "电力公用")),
    ("美联储",
     ("美联储", "FOMC", "鲍威尔", "点阵图", "联邦基金", "美债收益率"),
     ("金融", "有色贵金属")),
    ("地缘冲突",
     ("地缘冲突", "中东局势", "红海", "俄乌", "美伊", "伊朗", "以色列", "胡塞"),
     ("煤炭石油", "有色贵金属", "军工")),
)

# 主线注册表（无数据的主线也展示，供主线聚合接口遍历）
MAINLINE_NAMES: tuple[str, ...] = tuple(name for name, _, _ in MAINLINE_RULES)


def tag_mainline(title: str | None, summary: str | None = None) -> list[str]:
    """资讯标题/摘要 → 长期主线标签列表（空 = 非主线资讯）

    判定规则与 tag_long_term 一致：标题命中任一关键词即打标；标题未命中时，
    摘要需累计命中 >=2 个关键词才打标。
    """
    title = (title or "").strip()
    summary = (summary or "").strip()
    if not title:
        return []

    tags: list[str] = []
    for name, keywords, _ in MAINLINE_RULES:
        if any(k in title for k in keywords):
            tags.append(name)

    if not tags and summary:
        hits = sum(1 for _, keywords, _ in MAINLINE_RULES for k in keywords if k in summary)
        if hits >= 2:
            for name, keywords, _ in MAINLINE_RULES:
                if any(k in summary for k in keywords):
                    tags.append(name)

    return list(dict.fromkeys(tags))


def themes_to_mainlines(themes: list[str] | tuple[str, ...]) -> list[str]:
    """轮动主题 → 关联主线列表（因子 mainline_heat 反查用）"""
    theme_set = set(themes)
    return [name for name, _, mapped in MAINLINE_RULES if theme_set & set(mapped)]
