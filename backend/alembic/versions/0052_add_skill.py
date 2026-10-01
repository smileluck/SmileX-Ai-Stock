"""add sys_skill table and skill menu

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-01

1. 新建 sys_skill（AI 技能包表）：启用的技能按 sort 排序在 Agent 对话时
   拼入系统提示词，指导 LLM 按技能指令行事。
2. 在「环境配置」目录（2942406616008042）下新增「Skills 管理」菜单及
   list/manage 两个按钮权限。

沿用 0051 约定：仅插菜单记录，不向 sys_role_menu 分配角色。
ID 编排：0051 已用到 ...8048，本迁移自 2942406616008049 起编。
"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0052'
down_revision: Union[str, Sequence[str], None] = '0051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 菜单 ID（环境配置目录 2942406616008042；0051 已用到 ...8048，自 8049 起编）----
_ENV_CONFIG_CATALOG_ID = 2942406616008042
_SKILL_MENU_ID = 2942406616008049
_BTN_LIST_ID = 2942406616008050
_BTN_MANAGE_ID = 2942406616008051

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

_MENU_BASE = {
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

_MENU_ROWS = [
    {
        'id': _SKILL_MENU_ID,
        'parent_id': _ENV_CONFIG_CATALOG_ID,
        'name': 'env-config_skill',
        'path': '/env-config/skill',
        'component': 'view.env-config_skill',
        'permission': 'skill:list',
        'meta_icon': 'mdi:brain',
        'meta_hidden': False,
        'type': 'MENU',
        'sort': 87,
        **_MENU_BASE,
    },
    {
        'id': _BTN_LIST_ID,
        'parent_id': _SKILL_MENU_ID,
        'name': 'env-config_skill_list',
        'path': None,
        'component': None,
        'permission': 'skill:list',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 1,
        **_MENU_BASE,
    },
    {
        'id': _BTN_MANAGE_ID,
        'parent_id': _SKILL_MENU_ID,
        'name': 'env-config_skill_manage',
        'path': None,
        'component': None,
        'permission': 'skill:manage',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 2,
        **_MENU_BASE,
    },
]

_MENU_ROW_IDS = [row['id'] for row in _MENU_ROWS]


def upgrade() -> None:
    op.create_table(
        'sys_skill',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='技能名称'),
        sa.Column('code', sa.String(length=50), nullable=False, comment='技能编码'),
        sa.Column('content', sa.Text(), nullable=False, comment='技能指令内容'),
        sa.Column('description', sa.String(length=500), nullable=True, comment='技能描述'),
        sa.Column('status', sa.Boolean(), nullable=False, comment='状态：True-启用，False-禁用'),
        sa.Column('sort', sa.Integer(), nullable=False, comment='排序（越小越靠前）'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI 技能包表',
    )
    op.create_index(op.f('ix_sys_skill_id'), 'sys_skill', ['id'], unique=True)
    op.create_index(op.f('ix_sys_skill_code'), 'sys_skill', ['code'], unique=True)

    op.bulk_insert(_MENU_TABLE, _MENU_ROWS)


def downgrade() -> None:
    op.execute(
        f"DELETE FROM sys_menu WHERE id IN ({', '.join(str(i) for i in _MENU_ROW_IDS)})"
    )
    op.drop_index(op.f('ix_sys_skill_code'), table_name='sys_skill')
    op.drop_index(op.f('ix_sys_skill_id'), table_name='sys_skill')
    op.drop_table('sys_skill')
