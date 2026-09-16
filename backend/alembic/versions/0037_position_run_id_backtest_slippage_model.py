"""add position run_id and backtest slippage_model

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-16

P3 绩效深化：
1. business_strategy_position 加 run_id（BigInteger 可空，索引）——建仓来源执行记录，
   存量为 NULL（历史数据不回填）
2. business_backtest 加 slippage_model（String(20) NOT NULL 默认 'fixed'）——
   fixed-固定百分比滑点，amp-振幅比例滑点
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0037'
down_revision: Union[str, Sequence[str], None] = '0036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'business_strategy_position',
        sa.Column('run_id', sa.BigInteger(), nullable=True,
                  comment='建仓来源执行记录 ID（2026-09-16 起写入，存量为 NULL）'),
    )
    op.create_index('ix_strategy_position_run', 'business_strategy_position', ['run_id'], unique=False)
    # slippage_model 为 NOT NULL：存量行需 server_default 回填 'fixed'，回填后去除默认值
    op.add_column(
        'business_backtest',
        sa.Column('slippage_model', sa.String(length=20), nullable=False,
                  server_default=sa.text("'fixed'"),
                  comment='滑点模型：fixed-固定百分比，amp-振幅比例（slippage_pct 改作振幅系数）'),
    )
    op.alter_column('business_backtest', 'slippage_model', server_default=None)


def downgrade() -> None:
    op.drop_column('business_backtest', 'slippage_model')
    op.drop_index('ix_strategy_position_run', table_name='business_strategy_position')
    op.drop_column('business_strategy_position', 'run_id')
