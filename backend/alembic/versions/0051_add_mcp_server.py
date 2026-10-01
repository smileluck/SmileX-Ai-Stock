"""add sys_mcp_server table, seed fqgate server and mcp-server menu

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-01

1. 新建 sys_mcp_server（外部 MCP 服务配置表）：启用的 server 工具在 Agent
   对话时动态注册进工具表（命名空间 mcp__<code>__<tool>）。
2. 种子一条 FQGate 服务（code=fqgate，Streamable HTTP 127.0.0.1:17281）。
3. 在「环境配置」目录（2942406616008042）下新增「MCP 服务」菜单及
   list/manage/test 三个按钮权限。

沿用 0043 约定：仅插菜单记录，不向 sys_role_menu 分配角色。
ID 编排：0049 已用到 ...8043，本迁移自 2942406616008044 起编。
"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0051'
down_revision: Union[str, Sequence[str], None] = '0050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 菜单 ID（环境配置目录 2942406616008042；0049 已用到 ...8043，自 8044 起编）----
_ENV_CONFIG_CATALOG_ID = 2942406616008042
_MCP_MENU_ID = 2942406616008044
_BTN_LIST_ID = 2942406616008045
_BTN_MANAGE_ID = 2942406616008046
_BTN_TEST_ID = 2942406616008047

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

_SERVER_TABLE = sa.table(
    'sys_mcp_server',
    sa.column('id', sa.BigInteger),
    sa.column('code', sa.String),
    sa.column('name', sa.String),
    sa.column('url', sa.String),
    sa.column('headers', sa.JSON),
    sa.column('enabled', sa.Boolean),
    sa.column('timeout_s', sa.Integer),
    sa.column('remark', sa.String),
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
        'id': _MCP_MENU_ID,
        'parent_id': _ENV_CONFIG_CATALOG_ID,
        'name': 'env-config_mcp-server',
        'path': '/env-config/mcp-server',
        'component': 'view.env-config_mcp-server',
        'permission': 'mcp:list',
        'meta_icon': 'mdi:server-network',
        'meta_hidden': False,
        'type': 'MENU',
        'sort': 86,
        **_MENU_BASE,
    },
    {
        'id': _BTN_LIST_ID,
        'parent_id': _MCP_MENU_ID,
        'name': 'env-config_mcp-server_list',
        'path': None,
        'component': None,
        'permission': 'mcp:list',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 1,
        **_MENU_BASE,
    },
    {
        'id': _BTN_MANAGE_ID,
        'parent_id': _MCP_MENU_ID,
        'name': 'env-config_mcp-server_manage',
        'path': None,
        'component': None,
        'permission': 'mcp:manage',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 2,
        **_MENU_BASE,
    },
    {
        'id': _BTN_TEST_ID,
        'parent_id': _MCP_MENU_ID,
        'name': 'env-config_mcp-server_test',
        'path': None,
        'component': None,
        'permission': 'mcp:test',
        'meta_icon': None,
        'meta_hidden': True,
        'type': 'BUTTON',
        'sort': 3,
        **_MENU_BASE,
    },
]

_MENU_ROW_IDS = [row['id'] for row in _MENU_ROWS]

_FQGATE_SERVER_ID = 2942406616008048


def upgrade() -> None:
    op.create_table(
        'sys_mcp_server',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('code', sa.String(length=50), nullable=False, comment='服务编码（工具命名空间）'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='服务名称'),
        sa.Column('url', sa.String(length=500), nullable=False, comment='MCP 端点 URL'),
        sa.Column('headers', sa.JSON(), nullable=True, comment='自定义请求头（JSON 对象）'),
        sa.Column('enabled', sa.Boolean(), nullable=False, comment='是否启用'),
        sa.Column('timeout_s', sa.Integer(), nullable=False, comment='调用超时（秒）'),
        sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
        sa.PrimaryKeyConstraint('id'),
        comment='外部 MCP 服务配置表',
    )
    op.create_index(op.f('ix_sys_mcp_server_id'), 'sys_mcp_server', ['id'], unique=True)
    op.create_index(op.f('ix_sys_mcp_server_code'), 'sys_mcp_server', ['code'], unique=True)

    op.bulk_insert(
        _SERVER_TABLE,
        [
            {
                'id': _FQGATE_SERVER_ID,
                'code': 'fqgate',
                'name': 'FQGate 行情数据服务',
                'url': 'http://127.0.0.1:17281/mcp',
                'headers': None,
                'enabled': True,
                'timeout_s': 30,
                'remark': 'FQGate 本地网关 MCP 端点（Streamable HTTP），提供行情/板块/资金等 32 个工具',
                'deleted_at': None,
                'created_at': _DT,
                'updated_at': None,
            }
        ],
    )

    op.bulk_insert(_MENU_TABLE, _MENU_ROWS)


def downgrade() -> None:
    op.execute(
        f"DELETE FROM sys_menu WHERE id IN ({', '.join(str(i) for i in _MENU_ROW_IDS)})"
    )
    op.execute(f"DELETE FROM sys_mcp_server WHERE id = {_FQGATE_SERVER_ID}")
    op.drop_index(op.f('ix_sys_mcp_server_code'), table_name='sys_mcp_server')
    op.drop_index(op.f('ix_sys_mcp_server_id'), table_name='sys_mcp_server')
    op.drop_table('sys_mcp_server')
