"""add backtest module

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-16

策略回测模块：新增 business_backtest（回测任务：参数快照/状态/绩效汇总/净值曲线）
与 business_backtest_trade（回测成交明细）两表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0033'
down_revision: Union[str, Sequence[str], None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'business_backtest',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('strategy_id', sa.BigInteger(), nullable=False, comment='策略 ID'),
        sa.Column('strategy_name', sa.String(length=100), nullable=False, comment='策略名称（回测发起时快照）'),
        sa.Column('start_date', sa.String(length=10), nullable=False, comment='回测开始日期 YYYY-MM-DD'),
        sa.Column('end_date', sa.String(length=10), nullable=False, comment='回测结束日期 YYYY-MM-DD'),
        sa.Column('initial_capital', sa.Numeric(precision=16, scale=2), nullable=False, comment='初始资金（元）'),
        sa.Column('slippage_pct', sa.Numeric(precision=8, scale=4), nullable=False, comment='滑点比例(%)，买卖双边'),
        sa.Column('commission_pct', sa.Numeric(precision=8, scale=4), nullable=False, comment='佣金比例(%)，万2.5=0.025，最低 5 元'),
        sa.Column('stamp_tax_pct', sa.Numeric(precision=8, scale=4), nullable=False, comment='印花税比例(%)，仅卖出收取'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='回测状态：running-运行中，success-成功，failed-失败'),
        sa.Column('error_msg', sa.Text(), nullable=True, comment='失败原因'),
        sa.Column('result', sa.JSON(), nullable=True, comment='绩效汇总：total_return_pct/annual_return_pct/max_drawdown_pct/sharpe/win_count/loss_count/win_rate/profit_factor/trade_count/final_equity/warnings'),
        sa.Column('equity_curve', sa.JSON(), nullable=True, comment='每日净值曲线：[{date, equity, cash, market_value}, ...]'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True, comment='开始执行时间'),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True, comment='执行完成时间'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='策略回测任务表',
    )
    op.create_index('ix_backtest_strategy_created', 'business_backtest', ['strategy_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_business_backtest_id'), 'business_backtest', ['id'], unique=True)
    op.create_table(
        'business_backtest_trade',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('backtest_id', sa.BigInteger(), nullable=False, comment='回测任务 ID'),
        sa.Column('stock_code', sa.String(length=20), nullable=False, comment='证券代码'),
        sa.Column('stock_name', sa.String(length=50), nullable=False, comment='证券简称'),
        sa.Column('action', sa.String(length=10), nullable=False, comment='成交动作：buy-买入，sell-卖出'),
        sa.Column('trade_date', sa.String(length=10), nullable=False, comment='成交日期 YYYY-MM-DD'),
        sa.Column('price', sa.Numeric(precision=16, scale=4), nullable=False, comment='成交价（含滑点）'),
        sa.Column('quantity', sa.Integer(), nullable=False, comment='成交数量（股，100 的整数倍）'),
        sa.Column('amount', sa.Numeric(precision=16, scale=2), nullable=False, comment='成交金额（元）'),
        sa.Column('fee', sa.Numeric(precision=16, scale=2), nullable=False, comment='交易费用（佣金+印花税，元）'),
        sa.Column('reason', sa.String(length=500), nullable=True, comment='买入理由（AI 信号原文）或卖出原因：stop_loss/target_reached/trailing_stop/ai_signal/backtest_end'),
        sa.Column('return_rate', sa.Numeric(precision=10, scale=4), nullable=True, comment='该笔收益率(%)，仅 sell 记录（相对买入成交价，不含费用）'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='策略回测成交明细表',
    )
    op.create_index('ix_backtest_trade_backtest', 'business_backtest_trade', ['backtest_id'], unique=False)
    op.create_index(op.f('ix_business_backtest_trade_id'), 'business_backtest_trade', ['id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_business_backtest_trade_id'), table_name='business_backtest_trade')
    op.drop_index('ix_backtest_trade_backtest', table_name='business_backtest_trade')
    op.drop_table('business_backtest_trade')
    op.drop_index(op.f('ix_business_backtest_id'), table_name='business_backtest')
    op.drop_index('ix_backtest_strategy_created', table_name='business_backtest')
    op.drop_table('business_backtest')
