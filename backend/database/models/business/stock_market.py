#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A股行情快照表
- 大盘指数日快照
- 大盘资金流日快照
- 行业/概念板块日快照
- 板块成分股日快照
- 涨停/炸板股池日快照
- 指数成分股快照（BaoStock）
"""

from datetime import date
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    Date,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import mapped_column, Mapped

from database.models.base import Base


class BusinessMarketIndexDaily(Base):
    """大盘指数日快照表"""

    __table_args__ = (
        UniqueConstraint(
            "record_date",
            "index_code",
            name="uk_market_index_daily_date_code",
        ),
        {"comment": "大盘指数日快照表"},
    )

    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="快照日期（本地时区）"
    )
    index_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="指数代码"
    )
    index_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="指数名称")
    latest_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="最新价", default=None
    )
    change_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="涨跌幅(%)", default=None
    )
    change_amount: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="涨跌额", default=None
    )
    volume: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="成交量(手)", default=None
    )
    turnover: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="成交额(元)", default=None
    )
    amplitude: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="振幅(%)", default=None
    )
    high: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="最高", default=None
    )
    low: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="最低", default=None
    )
    open: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="今开", default=None
    )
    prev_close: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="昨收", default=None
    )


class BusinessMarketFundFlow(Base):
    """大盘资金流日快照表"""

    __table_args__ = (
        UniqueConstraint(
            "record_date",
            name="uk_market_fund_flow_date",
        ),
        {"comment": "大盘资金流日快照表"},
    )

    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="快照日期（本地时区）"
    )
    main_net_inflow: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="主力净流入(元)", default=None
    )
    super_large_net_inflow: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="超大单净流入(元)", default=None
    )
    large_net_inflow: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="大单净流入(元)", default=None
    )
    medium_net_inflow: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="中单净流入(元)", default=None
    )
    small_net_inflow: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="小单净流入(元)", default=None
    )


class BusinessBoardDaily(Base):
    """行业/概念板块日快照表"""

    __table_args__ = (
        UniqueConstraint(
            "record_date",
            "board_type",
            "board_code",
            name="uk_board_daily_date_type_code",
        ),
        {"comment": "行业/概念板块日快照表"},
    )

    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="快照日期（本地时区）"
    )
    board_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="板块类型: industry/concept"
    )
    board_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="板块代码"
    )
    board_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="板块名称")
    change_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="涨跌幅(%)", default=None
    )
    turnover: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="成交额(元)", default=None
    )
    turnover_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="换手率(%)", default=None
    )
    volume: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="成交量(手)", default=None
    )
    net_inflow: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="主力净流入(元)", default=None
    )
    rising_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="上涨家数", default=None
    )
    falling_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="下跌家数", default=None
    )
    leading_stock_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="领涨股代码", default=None
    )
    leading_stock_name: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="领涨股名称", default=None
    )
    leading_stock_change_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="领涨股涨跌幅(%)", default=None
    )
    leading_stocks: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="领涨股前三名 [{code, name, change_pct}]，抓取层按板块内涨幅排序",
    )


class BusinessBoardStockDaily(Base):
    """板块成分股日快照表（轮动分析-板块内高低切换数据源）

    每日收盘后对活跃板块（行业全量 + 概念涨幅前 N）抓取板块内全部成分股快照，
    用于计算板块内部高位/低位股分层与高低切换信号。
    """

    __table_args__ = (
        UniqueConstraint(
            "record_date",
            "board_type",
            "board_code",
            "stock_code",
            name="uk_board_stock_daily_date_board_code",
        ),
        {"comment": "板块成分股日快照表"},
    )

    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="快照日期（本地时区）"
    )
    board_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="板块类型: industry/concept"
    )
    board_code: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="板块代码"
    )
    board_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="板块名称")
    stock_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="股票代码"
    )
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="股票名称")
    price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="最新价", default=None
    )
    change_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="当日涨跌幅(%)", default=None
    )
    amount: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="成交额(元)", default=None
    )
    turnover_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="换手率(%)", default=None
    )
    gain_5d: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="近5日涨跌幅(%)（数据源直接提供；无则读时按快照自累计）", default=None
    )
    gain_10d: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="近10日涨跌幅(%)（数据源直接提供；无则读时按快照自累计）", default=None
    )


class BusinessLimitUpStock(Base):
    """涨停/炸板股池日快照表（pool_type: limit_up=收盘封板, broken=涨停后炸板未封住）"""

    __table_args__ = (
        UniqueConstraint(
            "record_date",
            "stock_code",
            "pool_type",
            name="uk_limit_up_daily_date_code_type",
        ),
        {"comment": "涨停/炸板股池日快照表"},
    )

    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="快照日期（本地时区）"
    )
    stock_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="股票代码"
    )
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="股票名称")
    market_board: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="市场板块: main/chinext/star/bse"
    )
    pool_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        insert_default="limit_up",
        comment="池类型: limit_up=收盘封板 / broken=涨停后炸板未封住",
    )
    latest_price: Mapped[Optional[float]] = mapped_column(
        Numeric(16, 4), nullable=True, comment="最新价", default=None
    )
    change_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="涨跌幅(%)", default=None
    )
    turnover_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="换手率(%)", default=None
    )
    turnover: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="成交额(元)", default=None
    )
    amplitude: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="振幅(%)", default=None
    )
    seal_amount: Mapped[Optional[float]] = mapped_column(
        Numeric(20, 2), nullable=True, comment="封板资金(元)", default=None
    )
    first_limit_up_time: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="首次封板时间", default=None
    )
    last_limit_up_time: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="最后封板时间", default=None
    )
    break_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="炸板次数", default=None
    )
    consecutive_limit_up: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="连板数", default=None
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="所属行业", default=None
    )
    limit_up_reason: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="涨停原因", default=None
    )


class BusinessIndexConstituent(Base):
    """指数成分股快照表（BaoStock 拉取，当前覆盖沪深300/中证500）"""

    __table_args__ = (
        UniqueConstraint(
            "record_date",
            "index_code",
            "stock_code",
            name="uk_index_constituent_date_code",
        ),
        {"comment": "指数成分股快照表"},
    )

    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="快照日期（本地时区）"
    )
    index_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="指数代码，如 000300-沪深300"
    )
    index_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="指数名称")
    stock_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="成分股代码（6位）"
    )
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="成分股名称")
    weight: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, comment="权重(%)", default=None
    )
