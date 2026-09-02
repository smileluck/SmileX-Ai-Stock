"""rotation analysis: board stock daily table + rotation analysis menu

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-01

1. 新建 business_board_stock_daily 板块成分股日快照表（轮动分析-板块内高低切换数据源）：
   每日收盘后对活跃板块（行业全量 + 概念涨幅前 N）抓取全部成分股快照
2. 在「AI助手」一级目录下新增「轮动策略分析」子菜单(MENU) id=8032：
   读写权限复用已有 stock:board:list/sync 与 analysis:list/run 按钮，不新增 BUTTON 行
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '0030'
down_revision: Union[str, Sequence[str], None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 菜单 ID（AI 助手目录 8001；0026 起 8020-8029 已用，取 8032，sort=10 空缺位）----
_AI_DIR_ID = 2942406616008001
_ROTATION_MENU_ID = 8032

_DT = datetime(2026, 9, 1, 12, 0, 0)

_MENU_TABLE = sa.table(
    'sys_menu',
    sa.column('id', sa.BigInteger),
    sa.column('parent_id', sa.BigInteger),
    sa.column('name', sa.String),
    sa.column('path', sa.String),
    sa.column('component', sa.String),
    sa.column('redirect', sa.String),
    sa.column('permission', sa.String),
    sa.column('meta_icon', sa.String),
    sa.column('meta_hidden', sa.Boolean),
    sa.column('meta_affix', sa.Boolean),
    sa.column('meta_breadcrumb', sa.Boolean),
    sa.column('status', sa.Boolean),
    sa.column('type', sa.String),
    sa.column('sort', sa.Integer),
    sa.column('is_system', sa.Boolean),
    sa.column('meta_href', sa.String),
    sa.column('meta_keep_alive', sa.Boolean),
    sa.column('deleted_at', sa.DateTime),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
)


def _menu_row(menu_id, parent_id, name, path, component, permission, icon, menu_type, sort):
    return {
        'id': menu_id,
        'parent_id': parent_id,
        'name': name,
        'path': path,
        'component': component,
        'redirect': None,
        'permission': permission,
        'meta_icon': icon,
        'meta_hidden': False,
        'meta_affix': False,
        'meta_breadcrumb': True,
        'status': True,
        'type': menu_type,
        'sort': sort,
        'is_system': True,
        'meta_href': None,
        'meta_keep_alive': False,
        'deleted_at': None,
        'created_at': _DT,
        'updated_at': None,
    }


def upgrade() -> None:
    # ================================================================
    # 1. 板块成分股日快照表
    # ================================================================
    op.create_table(
        'business_board_stock_daily',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('record_date', sa.Date(), nullable=False, comment='快照日期（本地时区）'),
        sa.Column('board_type', sa.String(length=20), nullable=False, comment='板块类型: industry/concept'),
        sa.Column('board_code', sa.String(length=20), nullable=False, comment='板块代码'),
        sa.Column('board_name', sa.String(length=100), nullable=False, comment='板块名称'),
        sa.Column('stock_code', sa.String(length=20), nullable=False, comment='股票代码'),
        sa.Column('stock_name', sa.String(length=50), nullable=False, comment='股票名称'),
        sa.Column('price', sa.Numeric(16, 4), nullable=True, comment='最新价'),
        sa.Column('change_pct', sa.Numeric(8, 4), nullable=True, comment='当日涨跌幅(%)'),
        sa.Column('amount', sa.Numeric(20, 2), nullable=True, comment='成交额(元)'),
        sa.Column('turnover_rate', sa.Numeric(8, 4), nullable=True, comment='换手率(%)'),
        sa.Column('gain_5d', sa.Numeric(8, 4), nullable=True,
                  comment='近5日涨跌幅(%)（数据源直接提供；无则读时按快照自累计）'),
        sa.Column('gain_10d', sa.Numeric(8, 4), nullable=True,
                  comment='近10日涨跌幅(%)（数据源直接提供；无则读时按快照自累计）'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'record_date', 'board_type', 'board_code', 'stock_code',
            name='uk_board_stock_daily_date_board_code',
        ),
        comment='板块成分股日快照表',
    )
    op.create_index(op.f('ix_business_board_stock_daily_id'), 'business_board_stock_daily', ['id'], unique=True)
    op.create_index('ix_board_stock_daily_date_code', 'business_board_stock_daily', ['record_date', 'board_code'])
    op.create_index('ix_board_stock_daily_stock_code', 'business_board_stock_daily', ['stock_code'])

    # ================================================================
    # 2. 「轮动策略分析」菜单（读写复用 stock:board 与 analysis 既有按钮权限）
    # ================================================================
    op.bulk_insert(_MENU_TABLE, [
        _menu_row(
            _ROTATION_MENU_ID, _AI_DIR_ID,
            'ai_rotation-analysis', '/ai/rotation-analysis',
            'view.ai_rotation-analysis',
            'stock:board:list',
            'mdi:autorenew', 'MENU', 10,
        ),
    ])


def downgrade() -> None:
    op.execute(f"DELETE FROM sys_menu WHERE id = {_ROTATION_MENU_ID}")

    op.drop_index('ix_board_stock_daily_stock_code', table_name='business_board_stock_daily')
    op.drop_index('ix_board_stock_daily_date_code', table_name='business_board_stock_daily')
    op.drop_index(op.f('ix_business_board_stock_daily_id'), table_name='business_board_stock_daily')
    op.drop_table('business_board_stock_daily')
