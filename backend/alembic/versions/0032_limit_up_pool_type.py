"""limit up pool_type (broken board)

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-14

热门个股记录炸板股：business_limit_up_stock 新增 pool_type
（limit_up=收盘封板 / broken=涨停后炸板未封住），
唯一约束由 (record_date, stock_code) 扩展为 (record_date, stock_code, pool_type)。
存量行回填 limit_up。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0032'
down_revision: Union[str, Sequence[str], None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'business_limit_up_stock',
        sa.Column('pool_type', sa.String(20), nullable=False,
                  server_default='limit_up',
                  comment='池类型: limit_up=收盘封板 / broken=涨停后炸板未封住'),
    )
    op.create_index(
        'ix_business_limit_up_stock_pool_type',
        'business_limit_up_stock',
        ['pool_type'],
    )
    op.drop_constraint(
        'uk_limit_up_daily_date_code', 'business_limit_up_stock', type_='unique'
    )
    op.create_unique_constraint(
        'uk_limit_up_daily_date_code_type',
        'business_limit_up_stock',
        ['record_date', 'stock_code', 'pool_type'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uk_limit_up_daily_date_code_type', 'business_limit_up_stock', type_='unique'
    )
    op.create_unique_constraint(
        'uk_limit_up_daily_date_code',
        'business_limit_up_stock',
        ['record_date', 'stock_code'],
    )
    op.drop_index(
        'ix_business_limit_up_stock_pool_type', table_name='business_limit_up_stock'
    )
    op.drop_column('business_limit_up_stock', 'pool_type')
