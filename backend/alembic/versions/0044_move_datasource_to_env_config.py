"""move datasource menu under new env-config catalog

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-01

在「系统管理」目录下新建「环境配置」子目录（CATALOG），并把 0043 种下的
「数据源管理」菜单（2942406616008038）移入其中。

前端 dynamic 路由模式（VITE_AUTH_ROUTE_MODE=dynamic）按菜单 name 匹配组件，
菜单 name/path/component 均不变，页面组件解析不受影响；
多级目录经 elegant-router transform 拍平，CATALOG 行 component 必须为 NULL
（若写 layout.base 会导致双层布局嵌套）。
i18n 需配套补 route.manage_env-config 语言键（zh-cn/en-us）。
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '0044'
down_revision: Union[str, Sequence[str], None] = '0043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 菜单 ID（系统管理目录 2874692539129857；0043 已用到 ...8041，自 8042 起编）----
_MANAGE_DIR_ID = 2874692539129857
_ENV_CONFIG_CATALOG_ID = 2942406616008042
_DATASOURCE_MENU_ID = 2942406616008038

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

_CATALOG_ROW = {
    'id': _ENV_CONFIG_CATALOG_ID,
    'parent_id': _MANAGE_DIR_ID,
    'name': 'manage_env-config',
    'path': '/manage/env-config',
    # 多级目录必须 component=NULL：elegant-router transform 对非一级路由拍平，
    # 写 layout.base 会导致双层布局嵌套
    'component': None,
    'redirect': None,
    'permission': None,
    'meta_icon': 'mdi:cog-box-outline',
    'meta_hidden': False,
    'meta_affix': False,
    'meta_breadcrumb': True,
    'status': True,
    'type': 'CATALOG',
    'sort': 90,
    'is_system': True,
    'meta_href': None,
    'meta_keep_alive': False,
    'deleted_at': None,
    'created_at': _DT,
    'updated_at': None,
}


def upgrade() -> None:
    op.bulk_insert(_MENU_TABLE, [_CATALOG_ROW])
    op.execute(
        f"UPDATE sys_menu SET parent_id = {_ENV_CONFIG_CATALOG_ID} "
        f"WHERE id = {_DATASOURCE_MENU_ID}"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE sys_menu SET parent_id = {_MANAGE_DIR_ID} "
        f"WHERE id = {_DATASOURCE_MENU_ID}"
    )
    op.execute(f"DELETE FROM sys_menu WHERE id = {_ENV_CONFIG_CATALOG_ID}")
