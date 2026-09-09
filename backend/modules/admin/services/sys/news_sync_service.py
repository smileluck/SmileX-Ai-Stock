#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
新闻聚合抓取入库协调服务
遍历所有新闻源，抓取 -> 时间归一化 -> URL 去重入库 -> 记录采集日志
"""
import logging

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.business.news import BusinessNews, BusinessNewsSyncLog
from database.utils.timezone import timezone
from modules.admin.services.sys.news_fetcher import NEWS_SOURCES, parse_news_time
from modules.admin.services.sys.news_tagger import tag_long_term

logger = logging.getLogger(__name__)


class NewsSyncService:
    """新闻聚合抓取入库服务类"""

    @staticmethod
    async def sync_all(db: AsyncSession) -> dict:
        """抓取并入库所有新闻源。

        返回汇总：{fetched, saved, failed_sources}
        """
        fetched_total = 0
        saved_total = 0
        failed_sources: list[dict] = []

        async with httpx.AsyncClient(headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }) as client:
            for source in NEWS_SOURCES:
                key = source["key"]
                name = source["name"]
                started_at = timezone.now()
                try:
                    raw_items = await source["fetch"](client, source["page_size"])
                    raw_items = [it for it in raw_items if it]
                    fetched_count = len(raw_items)

                    # 时间归一化 + 过滤缺标题/URL 的脏数据
                    rows = []
                    for it in raw_items:
                        published_at = parse_news_time(it.get("raw_time"))
                        # 长期事件打标（厄尔尼诺/减产/关税等长周期事件，空=短期资讯）
                        long_term_tags = tag_long_term(it.get("title"), it.get("summary"))
                        rows.append({
                            "title": it.get("title"),
                            "content": it.get("content"),
                            "summary": it.get("summary"),
                            "url": it.get("url"),
                            "source": key,
                            "source_name": name,
                            "author": it.get("author"),
                            "published_at": published_at,
                            "raw_time": it.get("raw_time"),
                            "long_term_tags": long_term_tags or None,
                            "created_at": timezone.now(),
                        })

                    # PostgreSQL INSERT ... ON CONFLICT DO NOTHING（按 url 去重）
                    saved_count = 0
                    if rows:
                        stmt = insert(BusinessNews).values(rows)
                        stmt = stmt.on_conflict_do_nothing(index_elements=["url"])
                        result = await db.execute(stmt)
                        saved_count = result.rowcount or 0

                    fetched_total += fetched_count
                    saved_total += saved_count
                    db.add(BusinessNewsSyncLog(
                        source=key,
                        status=True,
                        fetched_count=fetched_count,
                        saved_count=saved_count,
                        started_at=started_at,
                        finished_at=timezone.now(),
                    ))
                    await db.commit()
                    logger.info("新闻源 %s 抓取完成: fetched=%d saved=%d", key, fetched_count, saved_count)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("新闻源 %s 抓取失败: %s", key, exc)
                    await db.rollback()
                    failed_sources.append({"source": key, "error": str(exc)})
                    db.add(BusinessNewsSyncLog(
                        source=key,
                        status=False,
                        fetched_count=0,
                        saved_count=0,
                        error_msg=str(exc)[:1000],
                        started_at=started_at,
                        finished_at=timezone.now(),
                    ))
                    await db.commit()

        return {
            "fetched": fetched_total,
            "saved": saved_total,
            "failed_sources": failed_sources,
        }
