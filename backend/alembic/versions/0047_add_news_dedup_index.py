"""add business_news dedup index

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-01

资讯聚合列表查询始终按标题去重（row_number 窗口 partition by title），
过滤条件固定为 deleted_at IS NULL。无索引时窗口函数需对全表（27.9 万行 /
293MB）按 title 排序，分页数据查询 ~9.6s + count ~9s，接口总耗时 ~20s，
超出前端请求超时，页面表现为「无法加载数据」。

新增部分复合索引 (title, published_at DESC NULLS LAST, id DESC)
WHERE deleted_at IS NULL 后实测：分页查询 0.44s、count 0.06s。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0047'
down_revision: Union[str, Sequence[str], None] = '0046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_business_news_dedup',
        'business_news',
        ['title', sa.text('published_at DESC NULLS LAST'), sa.text('id DESC')],
        unique=False,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_business_news_dedup', table_name='business_news')
