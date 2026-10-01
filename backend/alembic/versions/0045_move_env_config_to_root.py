"""move env-config catalog to root level

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-01

把 0044 新建的「环境配置」目录从「系统管理」子目录提升为根级目录。

根级 CATALOG 按 0002 既有约定：name 不含下划线（elegant-router transform 以
name 是否含 "_" 判断一级路由，manage_env-config 含下划线会被当作非一级路由
拍平出错）、component='layout.base'。故同步改名 manage_env-config → env-config、
path /manage/env-config → /env-config。
子菜单 manage_datasource 不动（name 含 "_" 作为二级子路由正常）。
i18n 键 route.manage_env-config → route.env-config（前端语言包同步改）。
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0045'
down_revision: Union[str, Sequence[str], None] = '0044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENV_CONFIG_CATALOG_ID = 2942406616008042
_MANAGE_DIR_ID = 2874692539129857


def upgrade() -> None:
    op.execute(
        f"UPDATE sys_menu SET parent_id = NULL, name = 'env-config', "
        f"path = '/env-config', component = 'layout.base', sort = 9 "
        f"WHERE id = {_ENV_CONFIG_CATALOG_ID}"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE sys_menu SET parent_id = {_MANAGE_DIR_ID}, name = 'manage_env-config', "
        f"path = '/manage/env-config', component = NULL, sort = 90 "
        f"WHERE id = {_ENV_CONFIG_CATALOG_ID}"
    )
