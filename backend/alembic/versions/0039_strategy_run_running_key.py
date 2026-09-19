"""strategy run running unique key via generated column

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-19

business_strategy_run 加 running_key 生成列 + 唯一索引，
用生成列模拟「部分唯一索引」：仅 status='running' 的记录占用
strategy_id 键位（MySQL/PG 唯一索引均允许多个 NULL，非 running 行不受限），
DB 层兜底防止同策略并发提交出多条 running 记录（TOCTOU）。
生产 MySQL 使用 VIRTUAL 生成列；本地 PG（dev/test）降级为 STORED 生成列，语义一致。

【迁移前置清理】若库中存在同策略多条 running 脏数据，建唯一索引会失败，
需先执行：
    UPDATE business_strategy_run SET status='failed', error_msg='迁移前清理'
    WHERE status='running' AND created_at < NOW() - INTERVAL 15 MINUTE;
（仍有同策略同时 running 的需人工保留一条，其余同样置 failed）
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '0039'
down_revision: Union[str, Sequence[str], None] = '0038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 生成列表达式：CASE WHEN 在 MySQL 与 PostgreSQL 均可用（IF() 仅 MySQL）
_GENERATED_EXPR = "CASE WHEN status='running' THEN strategy_id ELSE NULL END"

# 「AI 分析」菜单（0015）下新增「持仓跟踪」按钮权限：POST /positions/track 会触发
# 自动平仓属写操作，不再挂在只读的 strategy:position:list 下
_STRATEGY_MENU_ID = 2942406616008008
_BTN_TRACK_ID = 2942406616008034  # 0015-0038 已用到 ...8033

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
    if op.get_bind().dialect.name == "mysql":
        # MySQL：VIRTUAL 生成列（不占存储），唯一索引允许多个 NULL
        op.execute(
            f"ALTER TABLE business_strategy_run "
            f"ADD COLUMN running_key BIGINT "
            f"GENERATED ALWAYS AS ({_GENERATED_EXPR}) VIRTUAL "
            f"COMMENT '运行唯一键（生成列）：status=running 时为 strategy_id，否则 NULL'"
        )
    else:
        # PostgreSQL（本地 dev/test）：仅支持 STORED 生成列，语义一致
        op.add_column(
            'business_strategy_run',
            sa.Column(
                'running_key', sa.BigInteger(),
                sa.Computed(_GENERATED_EXPR),
                nullable=True,
                comment='运行唯一键（生成列）：status=running 时为 strategy_id，否则 NULL',
            ),
        )
    op.create_unique_constraint(
        'uq_strategy_run_running', 'business_strategy_run', ['running_key']
    )

    # 种子：「持仓跟踪」按钮权限（与 0015 的 _btn_row 结构一致）
    op.bulk_insert(_MENU_TABLE, [{
        'id': _BTN_TRACK_ID,
        'parent_id': _STRATEGY_MENU_ID,
        'name': 'position_track',
        'path': None,
        'component': None,
        'redirect': None,
        'permission': 'strategy:position:track',
        'meta_icon': None,
        'meta_hidden': True,
        'meta_affix': False,
        'meta_breadcrumb': True,
        'status': True,
        'type': 'BUTTON',
        'sort': 4,
        'is_system': True,
        'meta_href': None,
        'meta_keep_alive': False,
        'deleted_at': None,
        'created_at': datetime(2026, 9, 19, 12, 0, 0),
        'updated_at': None,
    }])


def downgrade() -> None:
    op.execute(
        sa.delete(_MENU_TABLE).where(_MENU_TABLE.c.id == _BTN_TRACK_ID)
    )
    op.drop_constraint('uq_strategy_run_running', 'business_strategy_run', type_='unique')
    op.drop_column('business_strategy_run', 'running_key')
