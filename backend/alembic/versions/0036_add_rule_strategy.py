"""add rule strategy fields

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-16

business_ai_strategy 新增规则型策略字段：
1. strategy_type（String(20)，默认 'prompt'，索引）——prompt-LLM 提示词策略 / rule-规则型策略
2. rule_config（JSON，可空）——{"buy_conditions": [{factor_id, op, value}], "sell_conditions": [...]}，
   op ∈ gt/gte/lt/lte；prompt 型必须为 NULL
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0036'
down_revision: Union[str, Sequence[str], None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # strategy_type 为 NOT NULL：存量行需 server_default 回填 'prompt'，回填后去除默认值
    op.add_column(
        'business_ai_strategy',
        sa.Column('strategy_type', sa.String(length=20), nullable=False,
                  server_default=sa.text("'prompt'"),
                  comment='策略类型：prompt-LLM 提示词策略，rule-规则型策略（因子条件固化）；创建后不可改'),
    )
    op.alter_column('business_ai_strategy', 'strategy_type', server_default=None)
    op.add_column(
        'business_ai_strategy',
        sa.Column('rule_config', sa.JSON(), nullable=True,
                  comment='规则型策略配置：{"buy_conditions": [{factor_id, op, value}], '
                          '"sell_conditions": [...]}，op ∈ gt/gte/lt/lte；prompt 型必须为 NULL'),
    )
    op.create_index('ix_ai_strategy_strategy_type', 'business_ai_strategy', ['strategy_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_strategy_strategy_type', table_name='business_ai_strategy')
    op.drop_column('business_ai_strategy', 'rule_config')
    op.drop_column('business_ai_strategy', 'strategy_type')
