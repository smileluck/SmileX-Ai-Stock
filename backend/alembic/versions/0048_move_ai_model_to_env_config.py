"""move ai_model menu under env-config catalog

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-01

把「LLM配置」菜单从「AI助手」目录移动到根级「环境配置」目录下。

同 0046 的约束：前端 i18n route 语言键类型由 elegant-router 从 src/views
目录生成，挂在 env-config 目录下要求路由名为 env-config_model，因此视图从
views/ai/model/ 迁至 views/env-config/model/（elegant-router 已重新生成
routes/imports/typings），语言键 route.ai_model → route.env-config_model。
按钮行（2942406616007002-005）name 仅展示用途，权限串 sys:ai_model:* 不变，
不动。
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0048'
down_revision: Union[str, Sequence[str], None] = '0047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AI_MODEL_MENU_ID = 2942406616007001
_AI_CATALOG_ID = 2942406616008001
_ENV_CONFIG_CATALOG_ID = 2942406616008042


def upgrade() -> None:
    op.execute(
        f"UPDATE sys_menu SET parent_id = {_ENV_CONFIG_CATALOG_ID}, "
        f"name = 'env-config_model', path = '/env-config/model', "
        f"component = 'view.env-config_model', sort = 80 "
        f"WHERE id = {_AI_MODEL_MENU_ID}"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE sys_menu SET parent_id = {_AI_CATALOG_ID}, "
        f"name = 'ai_model', path = '/ai/model', "
        f"component = 'view.ai_model', sort = 11 "
        f"WHERE id = {_AI_MODEL_MENU_ID}"
    )
