#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据源静态注册表

所有出站到外部数据源的调用都应以其 source_key 经过 core.datasource.gateway，
面板（/admin/datasource/list）展示的名称、分类、调用点均来自本表。
新增数据源时在此登记，并给一份 DEFAULT_SOURCE_CONFIGS 默认配置（config.py）。
"""

# source_key -> 静态元数据
SOURCE_REGISTRY: dict[str, dict] = {
    "eastmoney": {
        "name": "东方财富",
        "category": "行情/板块/资金流",
        "call_sites": [
            "backtest.market_data（日线/日历 akshare 主源）",
            "stock.market_fetcher（指数实时/历史、资金流）",
            "stock.board_fetcher（板块列表/成分股/资金流）",
            "stock.limit_up_fetcher（涨停/炸板池）",
            "stock.stock_hot_fetcher（人气榜）",
            "stock.block_trade_fetcher（大宗交易）",
            "research.research_fetcher（研报）",
            "financial.financial_service（个股信息）",
            "admin.news_fetcher（快讯）",
        ],
    },
    "sina": {
        "name": "新浪财经",
        "category": "实时行情/财报",
        "call_sites": [
            "stock._sina（hq.sinajs.cn 批量实时行情兜底）",
            "strategy.quote_helper（交易引擎每分钟实时价）",
            "stock.market_fetcher（指数实时/历史兜底）",
            "financial.financial_fetcher（财务指标 akshare-新浪）",
            "admin.news_fetcher（全球快讯）",
        ],
    },
    "baostock": {
        "name": "BaoStock",
        "category": "日线/指数成分",
        "call_sites": [
            "backtest.market_data（日线/日历降级源）",
            "stock._baostock（指数日线/成分股）",
        ],
    },
    "fqgate": {
        "name": "FQGate 同花顺网关",
        "category": "日线/实时行情（本机网关）",
        "call_sites": [
            "stock._fqgate（日K/交易日历/实时报价全链路兜底）",
        ],
    },
    "tencent": {
        "name": "腾讯财经",
        "category": "板块",
        "call_sites": ["stock.board_fetcher（板块列表降级源）"],
    },
    "ths": {
        "name": "同花顺",
        "category": "板块/涨停原因/热榜",
        "call_sites": [
            "stock.board_fetcher（板块列表/成分股降级源）",
            "stock.limit_up_fetcher（涨停原因）",
            "stock.stock_hot_fetcher（热榜）",
            "admin.news_fetcher（全球快讯）",
        ],
    },
    "xueqiu": {
        "name": "雪球",
        "category": "热榜",
        "call_sites": ["stock.stock_hot_fetcher（关注/讨论榜）"],
    },
    "cls": {
        "name": "财联社",
        "category": "新闻",
        "call_sites": ["admin.news_fetcher（电报）"],
    },
    "wscn": {
        "name": "华尔街见闻",
        "category": "新闻",
        "call_sites": ["admin.news_fetcher（快讯 ×10 栏目）"],
    },
    "yicai": {
        "name": "第一财经",
        "category": "新闻",
        "call_sites": ["admin.news_fetcher（最新快讯）"],
    },
    "jin10": {
        "name": "金十数据",
        "category": "新闻/宏观",
        "call_sites": [
            "admin.news_fetcher（快讯 ×2）",
            "macro.macro_fetcher（中美 CPI/PPI/货币供应）",
        ],
    },
    "futu": {
        "name": "富途",
        "category": "新闻",
        "call_sites": ["admin.news_fetcher（全球快讯）"],
    },
}
