"""一次性回填存量资讯的长期事件标签（long_term_tags）。

背景：迁移 0031 给 business_news 加 long_term_tags 后，采集链路只对新入库
资讯打标（按 url on_conflict_do_nothing，旧闻不会重打）。本脚本对近 90 天
存量资讯跑同一 tagger 回填，幂等可重复执行。

用法：
    cd backend && ENVIR=dev .venv/bin/python -m scripts.backfill_news_long_term_tags
"""
import asyncio
import os
import sys
from datetime import timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from database.db_manager import init_pool, close_pool
from database.manager.async_manager import get_session
from database.models.business.news import BusinessNews
from database.utils.timezone import timezone
from modules.admin.services.sys.news_tagger import tag_long_term

_DAYS = 90


async def main() -> None:
    await init_pool()
    try:
        async for db in get_session():
            since = timezone.now() - timedelta(days=_DAYS)
            rows = (await db.execute(
                select(BusinessNews).where(
                    BusinessNews.published_at >= since,
                    BusinessNews.deleted_at.is_(None),
                )
            )).scalars().all()

            tagged = updated = 0
            for n in rows:
                tags = tag_long_term(n.title, n.summary)
                if tags:
                    tagged += 1
                new_val = tags or None
                if n.long_term_tags != new_val:
                    n.long_term_tags = new_val
                    updated += 1
            await db.commit()
            print(f"扫描近{_DAYS}天资讯 {len(rows)} 条，命中长期事件 {tagged} 条，更新 {updated} 条")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
