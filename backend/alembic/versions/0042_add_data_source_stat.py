"""add data source stat table

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-29

新建 sys_data_source_stat（数据源用量小时聚合统计表），
由 core.datasource.stats 内存聚合、调度任务 datasource.stats_flush 定时刷盘。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0042'
down_revision: Union[str, Sequence[str], None] = '0041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sys_data_source_stat',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('source_key', sa.String(length=30), nullable=False,
                  comment='数据源标识（core.datasource.registry）'),
        sa.Column('stat_hour', sa.DateTime(timezone=True), nullable=False,
                  comment='统计小时桶（整点）'),
        sa.Column('total_calls', sa.Integer(), nullable=False, comment='总调用次数'),
        sa.Column('success_calls', sa.Integer(), nullable=False, comment='成功次数'),
        sa.Column('fail_calls', sa.Integer(), nullable=False, comment='失败次数'),
        sa.Column('timeout_calls', sa.Integer(), nullable=False, comment='超时次数'),
        sa.Column('rejected_calls', sa.Integer(), nullable=False, comment='被禁用/熔断拒绝次数'),
        sa.Column('total_latency_ms', sa.BigInteger(), nullable=False,
                  comment='总耗时（毫秒，求平均用）'),
        sa.Column('max_latency_ms', sa.Integer(), nullable=False, comment='单次最大耗时（毫秒）'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_key', 'stat_hour', name='uq_data_source_stat_hour'),
        comment='数据源用量小时聚合统计表',
    )
    op.create_index(op.f('ix_sys_data_source_stat_id'), 'sys_data_source_stat', ['id'], unique=True)
    op.create_index(op.f('ix_sys_data_source_stat_source_key'), 'sys_data_source_stat', ['source_key'])


def downgrade() -> None:
    op.drop_index(op.f('ix_sys_data_source_stat_source_key'), table_name='sys_data_source_stat')
    op.drop_index(op.f('ix_sys_data_source_stat_id'), table_name='sys_data_source_stat')
    op.drop_table('sys_data_source_stat')
