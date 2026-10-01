"""seed fqgate demo menu under env-config catalog

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-01

在「环境配置」目录下新增「FQGate 演示」菜单，内嵌外部页面
https://fqgate.github.io/demo/。

不用 meta_href 外链方案：href 菜单 component 为 NULL，仅由路由守卫拦截
window.open 新标签页打开，且 i18n 键 route.<name> 不在 elegant-router 生成的
I18nRouteKey 内（纯 DB 菜单无对应 views 目录），locale 补键过不了 typecheck、
不补则菜单显示原始键名。故采用 iframe 内嵌：视图 views/env-config/fqgate/
存在则 route.env-config_fqgate 键合法（同 0046 的约束）。

ID 编排：0043 已用到 2942406616008041，0042 是 env-config 目录本身，
本菜单自 2942406616008043 起编。无按钮行（纯展示页，无需权限串）。
"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0049'
down_revision: Union[str, Sequence[str], None] = '0048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENV_CONFIG_CATALOG_ID = 2942406616008042
_FQGATE_MENU_ID = 2942406616008043

_DT = datetime(2026, 10, 1, 12, 0, 0)

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


def upgrade() -> None:
    op.bulk_insert(
        _MENU_TABLE,
        [
            {
                'id': _FQGATE_MENU_ID,
                'parent_id': _ENV_CONFIG_CATALOG_ID,
                'name': 'env-config_fqgate',
                'path': '/env-config/fqgate',
                'component': 'view.env-config_fqgate',
                'redirect': None,
                'permission': None,
                'meta_icon': 'mdi:gate',
                'meta_hidden': False,
                'meta_affix': False,
                'meta_breadcrumb': True,
                'status': True,
                'type': 'MENU',
                'sort': 85,
                'is_system': True,
                'meta_href': None,
                'meta_keep_alive': False,
                'deleted_at': None,
                'created_at': _DT,
                'updated_at': None,
            }
        ],
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM sys_menu WHERE id = {_FQGATE_MENU_ID}")
