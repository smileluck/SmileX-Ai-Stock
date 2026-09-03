#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
板块轮动分析 Schema
"""
from datetime import date

from pydantic import Field

from modules.common.schemas.base import BaseEntity

# 轮动阶段（规则计算）：start-低位启动 / ferment-发酵 / climax-高潮 / ebb-退潮 / observe-蓄势观察
ROTATION_STAGES = ("start", "ferment", "climax", "ebb", "observe")

# 明日操作建议：attack-主攻 / ambush-潜伏埋伏 / avoid-回避 / watch-观察
ROTATION_ACTIONS = ("attack", "ambush", "avoid", "watch")

# 高低切换信号：switching-高低切换 / split-分歧 / resonance-共振 / unknown-数据不足
SWITCH_SIGNALS = ("switching", "split", "resonance", "unknown")

# 主题热度状态：gathering-集结升温(多板块同动且低位，埋伏窗口) / active-发酵走强 /
# hot-高位过热 / cooling-退潮 / flat-平静
ROTATION_THEME_STATUSES = ("gathering", "active", "hot", "cooling", "flat")


class RotationOverviewItem(BaseEntity):
    """近期轮动板块指标项（读时计算，不入库）"""

    board_type: str = Field(..., description="板块类型: industry/concept")
    board_code: str
    board_name: str
    change_pct: float | None = Field(None, description="今日涨跌幅(%)")
    gain_3d: float | None = Field(None, description="近3日累计涨跌幅(%)")
    gain_5d: float | None = Field(None, description="近5日累计涨跌幅(%)")
    gain_10d: float | None = Field(None, description="近10日累计涨跌幅(%)")
    rank: int | None = Field(None, description="今日涨幅排名(升序，1=最强)")
    rank_change: int | None = Field(
        None, description="排名变化 = 5日前排名 - 今日排名，正数=排名上升"
    )
    volume_ratio: float | None = Field(
        None, description="量比 = 今日成交额 / 前5日成交额均值"
    )
    inflow_days: int | None = Field(
        None, ge=0, description="主力净流入连续为正的交易日数（从今日往回数）"
    )
    limit_up_count: int | None = Field(
        None, ge=0, description="近3日板块内涨停家数（去重）"
    )
    max_consecutive: int | None = Field(
        None, ge=0, description="近3日板块内最高连板数"
    )
    stage: str = Field(..., description="轮动阶段: start/ferment/climax/ebb/observe")
    tomorrow_score: int = Field(
        ..., ge=0, le=100, description="明日轮动候选评分 0-100（规则计算）"
    )
    action: str = Field(..., description="操作建议: attack/ambush/avoid/watch")
    theme: str | None = Field(
        None, description="所属主题（板块名关键词聚合，如 军工/算力AI/医药医疗）"
    )
    position_pct: float | None = Field(
        None, ge=0, le=1, description="近10日涨幅位置百分位（0=全体最低位，1=最高位）"
    )


class RotationThemeItem(BaseEntity):
    """主题热度项（跨行业+概念按关键词聚合，读时计算）"""

    theme: str
    member_count: int = Field(..., ge=0, description="主题内成员板块数")
    avg_change_pct: float | None = Field(None, description="成员今日平均涨幅(%)")
    avg_gain_3d: float | None = Field(None, description="成员近3日平均涨幅(%)")
    avg_gain_5d: float | None = Field(None, description="成员近5日平均涨幅(%)")
    rising_ratio_3d: float | None = Field(
        None, ge=0, le=1, description="近3日成员上涨占比（多板块同动=资金集结）"
    )
    inflow_ratio: float | None = Field(
        None, ge=0, le=1, description="今日成员净流入为正占比"
    )
    avg_position_pct: float | None = Field(
        None, ge=0, le=1, description="成员近10日位置百分位均值（低=低位）"
    )
    limit_up_total: int = Field(..., ge=0, description="近3日成员涨停家数合计")
    heat: int = Field(..., ge=0, le=100, description="主题热度 0-100（广度40+动量25+资金20+低位15）")
    status: str = Field(
        ..., description="主题状态: gathering/active/hot/cooling/flat"
    )


class RotationOverviewResponse(BaseEntity):
    """近期轮动板块总览"""

    snapshot_date: date | None = Field(None, description="最新快照日期")
    history_days: int = Field(..., description="实际可用的历史交易日数")
    items: list[RotationOverviewItem] = Field(
        default_factory=list, description="按明日候选评分降序"
    )
    themes: list[RotationThemeItem] = Field(
        default_factory=list, description="主题热度（跨行业+概念聚合，按热度降序）"
    )


class RotationSwitchStockItem(BaseEntity):
    """高低切换个股明细项"""

    stock_code: str
    stock_name: str
    price: float | None = None
    change_pct: float | None = Field(None, description="今日涨跌幅(%)")
    amount: float | None = Field(None, description="今日成交额(元)")
    position_gain: float | None = Field(
        None, description="位置涨幅(%)：近10日，缺失时近5日，再缺失当日"
    )


class RotationSwitchItem(BaseEntity):
    """板块内高低切换信号项"""

    board_type: str
    board_code: str
    board_name: str
    change_pct: float | None = Field(None, description="板块今日涨跌幅(%)")
    signal: str = Field(..., description="信号: switching/split/resonance/unknown")
    high_avg_pct: float | None = Field(None, description="高位组（位置前20%）今日平均涨幅(%)")
    low_avg_pct: float | None = Field(None, description="低位组（位置后20%）今日平均涨幅(%)")
    position_key: str = Field(..., description="分层使用字段: gain_10d/gain_5d/change_pct")
    high_laggards: list[RotationSwitchStockItem] = Field(
        default_factory=list, description="高位滞涨股前5（高位组中今日表现最差）"
    )
    low_starters: list[RotationSwitchStockItem] = Field(
        default_factory=list, description="低位启动股前5（低位组中今日表现最好）"
    )


class RotationSwitchResponse(BaseEntity):
    """板块内高低切换总览"""

    snapshot_date: date | None = Field(None, description="成分股快照日期")
    items: list[RotationSwitchItem] = Field(
        default_factory=list, description="按板块今日涨幅降序"
    )


class RotationSyncResult(BaseEntity):
    """板块成分股快照同步结果"""

    boards: int = Field(..., ge=0, description="计划同步板块数")
    saved_boards: int = Field(..., ge=0, description="成功板块数")
    stocks: int = Field(..., ge=0, description="写入成分股记录数")
    failed_boards: int = Field(..., ge=0, description="失败板块数")
    snapshot_date: date | None = None


class RotationBackfillResult(BaseEntity):
    """板块历史回填提交结果（后台任务执行）"""

    board_type: str
    days: int
    boards: int = Field(..., ge=0, description="待回填板块数")
    status: str = Field("running", description="submitted-已提交后台执行")
