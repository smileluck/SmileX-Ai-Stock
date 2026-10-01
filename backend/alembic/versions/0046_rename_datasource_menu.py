"""rename datasource menu to env-config_datasource

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-01

前端 i18n route 语言键类型为 Record<I18nRouteKey, string>，I18nRouteKey 由
elegant-router 从 src/views 目录生成——纯 DB 目录（无对应 views 目录）的 key
无法通过 typecheck。故将视图迁至 views/env-config/datasource/ 并重新生成路由，
菜单同步改名 manage_datasource → env-config_datasource（path /env-config/datasource、
component view.env-config_datasource）。
按钮行（8039-8041）name 仅为展示用途，权限串 datasource:* 不变，不动。
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0046'
down_revision: Union[str, Sequence[str], None] = '0045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DATASOURCE_MENU_ID = 2942406616008038


def upgrade() -> None:
    op.execute(
        f"UPDATE sys_menu SET name = 'env-config_datasource', "
        f"path = '/env-config/datasource', component = 'view.env-config_datasource' "
        f"WHERE id = {_DATASOURCE_MENU_ID}"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE sys_menu SET name = 'manage_datasource', "
        f"path = '/manage/datasource', component = 'view.manage_datasource' "
        f"WHERE id = {_DATASOURCE_MENU_ID}"
    )
