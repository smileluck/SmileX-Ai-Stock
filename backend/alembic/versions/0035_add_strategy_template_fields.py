"""add strategy template fields

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-16

business_ai_strategy 新增模板市场字段：
1. is_template（Boolean，默认 False，索引）——是否已发布为模板
2. source_id（BigInteger，可空，索引）——克隆/导入来源策略 ID
3. tags（JSON，可空）——字符串列表标签，如 ["打板", "短线"]
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0035'
down_revision: Union[str, Sequence[str], None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # is_template 为 NOT NULL：存量行需 server_default 回填 False，回填后去除默认值
    op.add_column(
        'business_ai_strategy',
        sa.Column('is_template', sa.Boolean(), nullable=False,
                  server_default=sa.text('false'), comment='是否已发布为模板（模板市场可见）'),
    )
    op.alter_column('business_ai_strategy', 'is_template', server_default=None)
    op.add_column(
        'business_ai_strategy',
        sa.Column('source_id', sa.BigInteger(), nullable=True, comment='克隆/导入来源策略 ID'),
    )
    op.add_column(
        'business_ai_strategy',
        sa.Column('tags', sa.JSON(), nullable=True, comment='标签列表，如 ["打板", "短线"]'),
    )
    op.create_index('ix_ai_strategy_is_template', 'business_ai_strategy', ['is_template'], unique=False)
    op.create_index('ix_ai_strategy_source_id', 'business_ai_strategy', ['source_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_strategy_source_id', table_name='business_ai_strategy')
    op.drop_index('ix_ai_strategy_is_template', table_name='business_ai_strategy')
    op.drop_column('business_ai_strategy', 'tags')
    op.drop_column('business_ai_strategy', 'source_id')
    op.drop_column('business_ai_strategy', 'is_template')
