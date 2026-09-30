"""seed datasource menu

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-29

在「系统管理」目录下新增「数据源管理」菜单（MENU）及 list/config/test 三个按钮权限。

沿用 0004/0014/0041 约定：仅插菜单记录，不向 sys_role_menu 分配任何角色 ——
超管用户自动可见，其他角色上线后由运维在角色管理页勾选。

菜单 name 与前端 elegant-router 路由名一致（manage_datasource），
前端按菜单 name 解析组件与 i18n（route.manage_datasource）。
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '0043'
down_revision: Union[str, Sequence[str], None] = '0042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 菜单 ID（系统管理目录 2874692539129857；0041 已用到 ...8037，自 8038 起编）----
_MANAGE_DIR_ID = 2874692539129857
_DATASOURCE_MENU_ID = 2942406616008038
_BTN_LIST_ID = 2942406616008039
_BTN_CONFIG_ID = 2942406616008040
_BTN_TEST_ID = 2942406616008041

_DT = datetime(2026, 9, 29, 12, 0, 0)

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
    'redirect': None,
    'meta_affix': False,
    'meta_breadcrumb': True,
    'status': True,
    'is_system': True,
    'meta_href': None,
    'meta_keep_alive': False,
    'deleted_at': None,
    'created_at': _DT,
    'updated_at': None,
}

_ROWS = [
    {
        'id': _DATASOURCE_MENU_ID,
        'parent_id': _MANAGE_DIR_ID,
        'name': 'manage_datasource',
        'path': '/manage/datasource',
        'component': 'view.manage_datasource',
        'permission': 'datasource:list',
        'meta_icon': 'mdi:database-cog-outline',
        'meta_hidden': False,
        'type': 'MENU',
        'sort': 90,
        **_BASE,
    },
    {
        'id': _BTN_LIST_ID,
        'parent_id': _DATASOURCE_MENU_ID,
        'name': 'manage_datasource_list',
        'path': None,
        'component': None,
        'permission': 'datasource:list',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 1,
        **_BASE,
    },
    {
        'id': _BTN_CONFIG_ID,
        'parent_id': _DATASOURCE_MENU_ID,
        'name': 'manage_datasource_config',
        'path': None,
        'component': None,
        'permission': 'datasource:config',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 2,
        **_BASE,
    },
    {
        'id': _BTN_TEST_ID,
        'parent_id': _DATASOURCE_MENU_ID,
        'name': 'manage_datasource_test',
        'path': None,
        'component': None,
        'permission': 'datasource:test',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 3,
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
