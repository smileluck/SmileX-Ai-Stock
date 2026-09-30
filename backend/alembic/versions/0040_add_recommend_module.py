"""add recommend module

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-29

1. 新建 business_recommend_run（AI 推荐执行记录）与 business_recommend_stock
   （推荐个股，含预判买点/目标价/止损价与关联信号 ID）两张表
2. business_strategy_signal 新增 entry_type 列（建仓方式：market/limit），
   server_default='market' 保证存量行兼容（既有信号维持实时价直接成交语义）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0040'
down_revision: Union[str, Sequence[str], None] = '0039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ================================================================
    # 1. AI 推荐执行记录表
    # ================================================================
    op.create_table(
        'business_recommend_run',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('run_date', sa.Date(), nullable=False, comment='推荐日期（本地时区）'),
        sa.Column('trigger_type', sa.String(length=20), nullable=False,
                  comment='触发方式：schedule-定时，manual-手动'),
        sa.Column('status', sa.String(length=20), nullable=False,
                  comment='执行状态：running-执行中，success-成功，failed-失败'),
        sa.Column('error_msg', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('ai_raw_response', sa.Text(), nullable=True,
                  comment='AI 原始回复文本（json 块 + markdown 综合研判）'),
        sa.Column('parsed_result', sa.JSON(), nullable=True,
                  comment='解析后的结构化推荐结果：{"stocks": [...]}'),
        sa.Column('candidate_snapshot', sa.JSON(), nullable=True,
                  comment='候选池摘要：六维度候选股及其量化线索'),
        sa.Column('strategy_id', sa.BigInteger(), nullable=True,
                  comment='关联的专用策略 ID（AI每日推荐，信号落库到该策略下）'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI 推荐执行记录表',
    )
    op.create_index(op.f('ix_business_recommend_run_id'), 'business_recommend_run', ['id'], unique=True)
    op.create_index('ix_recommend_run_date', 'business_recommend_run', ['run_date'])

    # ================================================================
    # 2. AI 推荐个股表
    # ================================================================
    op.create_table(
        'business_recommend_stock',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('run_id', sa.BigInteger(), nullable=False, comment='推荐执行记录 ID'),
        sa.Column('rank', sa.SmallInteger(), nullable=False, comment='推荐排序（按评分降序 1-10）'),
        sa.Column('stock_code', sa.String(length=20), nullable=False, comment='证券代码'),
        sa.Column('stock_name', sa.String(length=50), nullable=False, comment='证券简称'),
        sa.Column('direction', sa.String(length=20), nullable=False,
                  comment='推荐方向：limit_up-涨停候选，bottom_fish-抄底'),
        sa.Column('score', sa.Numeric(6, 2), nullable=False, comment='综合评分 0-100'),
        sa.Column('buy_price', sa.Numeric(16, 4), nullable=True, comment='预判买点（参考买价）'),
        sa.Column('target_price', sa.Numeric(16, 4), nullable=True, comment='目标价（预估卖点）'),
        sa.Column('stop_loss_price', sa.Numeric(16, 4), nullable=True, comment='止损价'),
        sa.Column('entry_type', sa.String(length=16), nullable=False,
                  comment='建仓方式：market-按实时价直接成交，limit-触及买点（实时价<=买点）才成交'),
        sa.Column('reasons', sa.JSON(), nullable=True,
                  comment='六维度小结论：{news,sentiment,factor,sector_fund,main_force,limit_up}'),
        sa.Column('summary', sa.String(length=500), nullable=True, comment='一句话推荐逻辑'),
        sa.Column('signal_id', sa.BigInteger(), nullable=True,
                  comment='关联的策略买入信号 ID（business_strategy_signal.id）'),
        sa.ForeignKeyConstraint(['run_id'], ['business_recommend_run.id']),
        sa.PrimaryKeyConstraint('id'),
        comment='AI 推荐个股表',
    )
    op.create_index(op.f('ix_business_recommend_stock_id'), 'business_recommend_stock', ['id'], unique=True)
    op.create_index('ix_recommend_stock_run', 'business_recommend_stock', ['run_id'])

    # ================================================================
    # 3. 策略信号表新增建仓方式列
    # ================================================================
    op.add_column(
        'business_strategy_signal',
        sa.Column('entry_type', sa.String(length=16), nullable=False,
                  server_default='market',
                  comment='建仓方式：market-按实时价直接成交，limit-触及参考买点（实时价<=ref_buy_price）才成交'),
    )


def downgrade() -> None:
    op.drop_column('business_strategy_signal', 'entry_type')

    op.drop_index('ix_recommend_stock_run', table_name='business_recommend_stock')
    op.drop_index(op.f('ix_business_recommend_stock_id'), table_name='business_recommend_stock')
    op.drop_table('business_recommend_stock')

    op.drop_index('ix_recommend_run_date', table_name='business_recommend_run')
    op.drop_index(op.f('ix_business_recommend_run_id'), table_name='business_recommend_run')
    op.drop_table('business_recommend_run')
