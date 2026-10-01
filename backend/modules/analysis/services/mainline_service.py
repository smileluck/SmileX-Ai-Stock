#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
长期主线聚合服务：LLM 主线分析（最近 news/morning 的 parsed_result.mainlines）
+ 主线分组资讯（注册表全量返回，无数据的主线 count=0）
"""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.business.analysis import BusinessAnalysisRun
from database.models.business.news import BusinessNews
from database.utils.timezone import timezone
from modules.admin.services.sys.news_tagger import MAINLINE_NAMES
from modules.analysis.schemas.analysis import (
    NewsMainlineAnalysisItem,
    NewsMainlineGroupItem,
    NewsMainlineNewsItem,
    NewsMainlinesResult,
)

logger = logging.getLogger(__name__)

_GROUP_DAYS = 7
_LATEST_PER_GROUP = 5


class MainlineService:
    """长期主线聚合服务类"""

    @staticmethod
    async def get_news_mainlines(db: AsyncSession) -> NewsMainlinesResult:
        # 1. 最近一次成功的 news/morning 分析中的 mainlines
        result = await db.execute(
            select(BusinessAnalysisRun)
            .where(
                BusinessAnalysisRun.analysis_type == "news",
                BusinessAnalysisRun.session == "morning",
                BusinessAnalysisRun.status == "success",
                BusinessAnalysisRun.deleted_at.is_(None),
            )
            .order_by(BusinessAnalysisRun.created_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        analysis = None
        analysis_time = None
        if run and run.parsed_result:
            raw_mainlines = run.parsed_result.get("mainlines")
            if isinstance(raw_mainlines, list):
                analysis = [
                    NewsMainlineAnalysisItem.model_validate(m)
                    for m in raw_mainlines
                    if isinstance(m, dict) and m.get("name")
                ]
                analysis_time = run.created_at

        # 2. 主线分组资讯：近 7 天带主线标签资讯，按注册表全量返回
        since = timezone.now() - timedelta(days=_GROUP_DAYS)
        news_result = await db.execute(
            select(BusinessNews)
            .where(
                BusinessNews.published_at >= since,
                BusinessNews.mainline_tags.isnot(None),
                BusinessNews.deleted_at.is_(None),
            )
            .order_by(BusinessNews.published_at.desc())
            .limit(2000)
        )
        rows = news_result.scalars().all()

        by_tag: dict[str, list] = {}
        counts: dict[str, int] = {}
        for n in rows:
            for tag in n.mainline_tags or []:
                counts[tag] = counts.get(tag, 0) + 1
                bucket = by_tag.setdefault(tag, [])
                if len(bucket) < _LATEST_PER_GROUP:
                    bucket.append(n)

        groups = [
            NewsMainlineGroupItem(
                name=name,
                news_count_7d=counts.get(name, 0),
                latest_news=[
                    NewsMainlineNewsItem(
                        id=n.id,
                        title=n.title,
                        source_name=n.source_name,
                        published_at=(
                            n.published_at.strftime("%Y-%m-%d %H:%M:%S") if n.published_at else None
                        ),
                    )
                    for n in by_tag.get(name, [])
                ],
            )
            for name in MAINLINE_NAMES
        ]
        groups.sort(key=lambda g: g.news_count_7d, reverse=True)

        return NewsMainlinesResult(analysis=analysis, analysis_time=analysis_time, groups=groups)
