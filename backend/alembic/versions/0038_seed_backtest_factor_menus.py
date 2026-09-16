"""seed backtest & factor menus

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-16

在「AI助手」一级目录下新增「策略回测」与「因子管理」两个子菜单（MENU）。

沿用 0004/0014 约定：仅插菜单记录，不向 sys_role_menu 分配任何角色 ——
超管用户自动可见（menu_service 超管分支取全部启用菜单），
其他角色上线后由运维在角色管理页勾选。

菜单 name 与前端 elegant-router 路由名一致（ai_backtest / ai_factor），
前端按菜单 name 解析组件与 i18n（route.ai_backtest / route.ai_factor 已存在）。
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None

_AI_DIR_ID = 2942406616008001
# 0030/0031 已被 research-report 按钮占用，自 0032 起编
_AI_BACKTEST_MENU_ID = 2942406616008032
_AI_FACTOR_MENU_ID = 2942406616008033
_DT = datetime(2026, 9, 16, 16, 0, 0)

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

_BASE = {
    'parent_id': _AI_DIR_ID,
    'redirect': None,
    'meta_hidden': False,
    'meta_affix': False,
    'meta_breadcrumb': True,
    'status': True,
    'type': 'MENU',
    'is_system': True,
    'meta_href': None,
    'meta_keep_alive': False,
    'deleted_at': None,
    'created_at': _DT,
    'updated_at': None,
}

_ROWS = [
    {
        'id': _AI_BACKTEST_MENU_ID,
        'name': 'ai_backtest',
        'path': '/ai/backtest',
        'component': 'view.ai_backtest',
        'permission': 'strategy:manage',
        'meta_icon': 'mdi:chart-timeline-variant',
        'sort': 12,
        **_BASE,
    },
    {
        'id': _AI_FACTOR_MENU_ID,
        'name': 'ai_factor',
        'path': '/ai/factor',
        'component': 'view.ai_factor',
        'permission': 'strategy:manage',
        'meta_icon': 'mdi:function-variant',
        'sort': 13,
        **_BASE,
    },
]

_ROW_IDS = [row['id'] for row in _ROWS]


def upgrade() -> None:
    op.bulk_insert(_MENU_TABLE, _ROWS)


def downgrade() -> None:
    op.execute(
        f"DELETE FROM sys_menu WHERE id IN ({', '.join(str(i) for i in _ROW_IDS)})"
    )
