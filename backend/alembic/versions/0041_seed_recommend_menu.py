"""seed recommend menu

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-29

在「AI助手」一级目录下新增「推荐板块」子菜单（MENU）及 list/run 两个按钮权限。

沿用 0004/0014 约定：仅插菜单记录，不向 sys_role_menu 分配任何角色 ——
超管用户自动可见（menu_service 超管分支取全部启用菜单），
其他角色上线后由运维在角色管理页勾选。

菜单 name 与前端 elegant-router 路由名一致（ai_stock-recommend），
前端按菜单 name 解析组件与 i18n（route.ai_stock-recommend）。
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '0041'
down_revision: Union[str, Sequence[str], None] = '0040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 菜单 ID（AI 助手目录 8001；0039 已用到 ...8034，自 8035 起编）----
_AI_DIR_ID = 2942406616008001
_RECOMMEND_MENU_ID = 2942406616008035
_BTN_LIST_ID = 2942406616008036
_BTN_RUN_ID = 2942406616008037

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
        'id': _RECOMMEND_MENU_ID,
        'parent_id': _AI_DIR_ID,
        'name': 'ai_stock-recommend',
        'path': '/ai/stock-recommend',
        'component': 'view.ai_stock-recommend',
        'permission': 'recommend:list',
        'meta_icon': 'mdi:star-four-points',
        'meta_hidden': False,
        'type': 'MENU',
        # 排序接在轮动策略分析（sort=10）之后、策略回测（sort=12）之前
        'sort': 11,
        **_BASE,
    },
    {
        'id': _BTN_LIST_ID,
        'parent_id': _RECOMMEND_MENU_ID,
        'name': 'stock-recommend_list',
        'path': None,
        'component': None,
        'permission': 'recommend:list',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 1,
        **_BASE,
    },
    {
        'id': _BTN_RUN_ID,
        'parent_id': _RECOMMEND_MENU_ID,
        'name': 'stock-recommend_run',
        'path': None,
        'component': None,
        'permission': 'recommend:run',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 2,
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
