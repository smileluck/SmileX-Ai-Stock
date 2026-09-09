"""news long_term_tags

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-09

长期资讯标记：business_news 新增 long_term_tags（JSON，空=短期资讯），
采集时按关键词规则打标（modules/admin/services/sys/news_tagger.py），
AI 分析注入时独立成段并赋予中线背景权重。
存量数据回填由 scripts/backfill_news_long_term_tags.py 手动执行。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0031'
down_revision: Union[str, Sequence[str], None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'business_news',
        sa.Column('long_term_tags', sa.JSON(), nullable=True,
                  comment='长期事件标签（空=短期资讯；标签口径同轮动主题，采集时按关键词规则打标）'),
    )


def downgrade() -> None:
    op.drop_column('business_news', 'long_term_tags')
