"""news mainline_tags

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-01

长期主线标记：business_news 新增 mainline_tags（JSON，空=非主线资讯）。
主线口径是事件/产业级（半导体/光通信/房地产/厄尔尼诺/美联储/地缘冲突等），
比 long_term_tags 的轮动主题口径更细，故独立成列不混用。
采集时按关键词规则打标（news_tagger.tag_mainline），每日资讯分析（news morning）
注入主线分组素材并要求 LLM 输出 parsed_result.mainlines；因子 DSL 新增
mainline_heat 字段（个股近5日关联主线资讯条数）。
存量数据回填由 scripts/backfill_news_mainline_tags.py 手动执行。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0050'
down_revision: Union[str, Sequence[str], None] = '0049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'business_news',
        sa.Column('mainline_tags', sa.JSON(), nullable=True,
                  comment='长期主线标签（空=非主线资讯；事件/产业级口径，采集时按关键词规则打标）'),
    )


def downgrade() -> None:
    op.drop_column('business_news', 'mainline_tags')
