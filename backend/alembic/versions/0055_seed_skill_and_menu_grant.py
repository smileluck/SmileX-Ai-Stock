"""seed: 预置 3 条 AI 技能 + 管理员角色菜单授权补齐

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-02

内容：
1. sys_skill 预置 3 条通用技能（数据引用规范/风险提示规范/A股数据口径备忘），
   默认 status=False 停用——不改变现有 Agent 行为，用户在 Skills 管理页按需启用。
2. 菜单授权补齐：0005 起各模块迁移沿用「仅插菜单不分配 sys_role_menu」约定，
   管理员角色（0002 的 ADMIN_ROLE_ID）只持有 0002 时期的菜单集，非超管的
   管理员角色用户看不到后续新模块。本迁移动态补齐 sys_menu 中全部未授权菜单，
   permission 沿用 0002 口径 'read'，ON CONFLICT DO NOTHING 天然幂等。

ID 台账：0054 已用到 ...9505；本迁移技能自 2942406616009601 起 3 条（至 9603）。

downgrade 说明：技能按 ID 段删除；菜单授权不做回删——删授权有把管理员角色
锁回旧菜单集的风险，且该操作本身幂等无害。
"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0055'
down_revision: Union[str, Sequence[str], None] = '0054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SKILL_ID_BASE = 2942406616009600
_ADMIN_ROLE_ID = 2874692539129900  # 0002 种子的管理员角色 ID
_DT = datetime(2026, 10, 2, 12, 0, 0)

# ----------------------------------------------------------------------
# 3 条预置技能（默认停用，启用后按 sort 顺序注入 Agent 系统提示词）
# ----------------------------------------------------------------------
_PRESET_SKILLS = [
    {
        'seq': 1, 'code': 'data_citation', 'name': '数据引用规范', 'sort': 10,
        'description': '约束 Agent 只引用工具返回的真实数据，禁止编造',
        'content': (
            '## 数据引用规范\n'
            '1. 所有价格、涨跌幅、成交量、资金流、财务与新闻数据，必须来自本次对话中'
            '工具调用的真实返回；工具未提供的数据一律回答「未获取到」，禁止凭记忆或推测编造。\n'
            '2. 引用数据时注明数据日期与来源口径（如：收盘价 2026-10-01，东财行情）。\n'
            '3. 同一字段多来源冲突时，优先采用实时行情源，并明确指出差异。\n'
            '4. 计算衍生指标（如乖离率、量比）时说明所用字段与计算口径。'
        ),
    },
    {
        'seq': 2, 'code': 'risk_disclaimer', 'name': '风险提示规范', 'sort': 20,
        'description': '买卖建议必须附带风险约束与失效条件',
        'content': (
            '## 风险提示规范\n'
            '1. 给出个股买入/卖出/持仓建议时，必须同步给出止损参考位与最大可接受回撤，'
            '禁止只讲收益不讲风险。\n'
            '2. 区分「事实」与「推断」：数据结论标注依据，推断结论标注逻辑链与失效条件。\n'
            '3. 涉及涨停打板、龙头战法等高风险风格时，必须提示情绪退潮与流动性风险。\n'
            '4. 任何建议末尾附一句：以上为量化信号与数据推演，不构成投资建议，'
            '请结合自身风险承受能力决策。'
        ),
    },
    {
        'seq': 3, 'code': 'a_share_conventions', 'name': 'A股数据口径备忘', 'sort': 30,
        'description': 'A股交易制度与常用数据口径，避免口径误用',
        'content': (
            '## A股数据口径备忘\n'
            '1. 涨跌幅 pct_chg 为百分数单位（如 5.0 表示 +5%）；振幅口径为 (high-low)/preclose。\n'
            '2. 量比 vr5 = 当日成交量 / 5 日均量；换手率为成交量占流通股本比例。\n'
            '3. 交易制度：T+1 买卖；涨跌停主板 ±10%、创业板/科创板 ±20%、北交所 ±30%、ST ±5%。\n'
            '4. 主力净流入为大单口径估算值，非精确机构行为，跨源数值可能不一致。\n'
            '5. 竞价时段（9:15-9:25）数据为撮合预览，开盘前可能因撤单变化。'
        ),
    },
]

_SKILL_TABLE = sa.table(
    'sys_skill',
    sa.column('id', sa.BigInteger),
    sa.column('deleted_at', sa.DateTime),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
    sa.column('name', sa.String),
    sa.column('code', sa.String),
    sa.column('content', sa.Text),
    sa.column('description', sa.String),
    sa.column('status', sa.Boolean),
    sa.column('sort', sa.Integer),
)


def upgrade() -> None:
    conn = op.get_bind()

    # ================================================================
    # 1. 幂等插入 3 条预置技能（按 code 查重，默认停用）
    # ================================================================
    existing_codes = {
        row[0] for row in conn.execute(
            sa.text("SELECT code FROM sys_skill WHERE deleted_at IS NULL")
        )
    }
    rows = []
    for item in _PRESET_SKILLS:
        if item['code'] in existing_codes:
            continue
        rows.append({
            'id': _SKILL_ID_BASE + item['seq'],
            'deleted_at': None,
            'created_at': _DT,
            'updated_at': None,
            'name': item['name'],
            'code': item['code'],
            'content': item['content'],
            'description': item['description'],
            'status': False,  # 预置技能默认停用，不改变现有 Agent 行为
            'sort': item['sort'],
        })
    if rows:
        op.bulk_insert(_SKILL_TABLE, rows)

    # ================================================================
    # 2. 菜单授权补齐：管理员角色 ← 全部未授权的未删除菜单
    # ================================================================
    op.execute(
        f"""
        INSERT INTO sys_role_menu (role_id, menu_id, permission)
        SELECT {_ADMIN_ROLE_ID}, m.id, 'read'
        FROM sys_menu m
        WHERE m.deleted_at IS NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # 技能按 ID 段删除；菜单授权不回删（见文件头说明）
    ids = ', '.join(str(_SKILL_ID_BASE + i['seq']) for i in _PRESET_SKILLS)
    op.execute(f"DELETE FROM sys_skill WHERE id IN ({ids})")
