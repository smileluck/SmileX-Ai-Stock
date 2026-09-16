"""add factor module

Revision ID: 0034
Revises: 17203a828aab
Create Date: 2026-09-16

1. 新建因子库表 business_factor（公式 DSL 因子 CRUD + 导入 + 计算 + 选股）
2. 幂等插入 17 条预置开源公式因子（source=preset，默认启用）：
   经典价量指标（BIAS/ROC/量比/波动率/振幅/RSI 等）+ WorldQuant Alpha101 节选
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '0034'
down_revision: Union[str, Sequence[str], None] = '17203a828aab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DT = datetime(2026, 9, 16, 12, 0, 0)

# 预置因子固定 ID 段（便于识别与幂等）
_PRESET_ID_BASE = 2942406616009200

# Alpha101 论文来源
_ALPHA101_URL = "https://arxiv.org/abs/1601.00991"

# ----------------------------------------------------------------------
# 17 条预置因子定义（公式经 modules/factor/services/formula.py 白名单校验）
# ----------------------------------------------------------------------
_PRESET_FACTORS = [
    {
        "seq": 1, "code": "bias5", "name": "BIAS5 乖离率",
        "category": "price",
        "formula": "(close - MA(close, 5)) / MA(close, 5) * 100",
        "description": "收盘价相对 5 日均线的偏离百分比，衡量短期超买超卖",
        "source_url": None,
    },
    {
        "seq": 2, "code": "bias10", "name": "BIAS10 乖离率",
        "category": "price",
        "formula": "(close - MA(close, 10)) / MA(close, 10) * 100",
        "description": "收盘价相对 10 日均线的偏离百分比",
        "source_url": None,
    },
    {
        "seq": 3, "code": "bias20", "name": "BIAS20 乖离率",
        "category": "price",
        "formula": "(close - MA(close, 20)) / MA(close, 20) * 100",
        "description": "收盘价相对 20 日均线的偏离百分比，中期超买超卖指标",
        "source_url": None,
    },
    {
        "seq": 4, "code": "roc5", "name": "ROC5 变动率",
        "category": "momentum",
        "formula": "DELTA(close, 5) / REF(close, 5) * 100",
        "description": "收盘价相对 5 日前的涨跌幅（%），短期动量",
        "source_url": None,
    },
    {
        "seq": 5, "code": "roc10", "name": "ROC10 变动率",
        "category": "momentum",
        "formula": "DELTA(close, 10) / REF(close, 10) * 100",
        "description": "收盘价相对 10 日前的涨跌幅（%）",
        "source_url": None,
    },
    {
        "seq": 6, "code": "roc20", "name": "ROC20 变动率",
        "category": "momentum",
        "formula": "DELTA(close, 20) / REF(close, 20) * 100",
        "description": "收盘价相对 20 日前的涨跌幅（%），中期动量",
        "source_url": None,
    },
    {
        "seq": 7, "code": "vr1", "name": "量比（1日）",
        "category": "volume",
        "formula": "volume / REF(volume, 1)",
        "description": "当日成交量相对前一日的倍数，衡量短期放量程度",
        "source_url": None,
    },
    {
        "seq": 8, "code": "vr5", "name": "量比（5日均量）",
        "category": "volume",
        "formula": "volume / MA(volume, 5)",
        "description": "当日成交量相对 5 日均量的倍数",
        "source_url": None,
    },
    {
        "seq": 9, "code": "vol20", "name": "20日波动率",
        "category": "volatility",
        "formula": "STD(pct_chg, 20)",
        "description": "20 日日收益率标准差（%），衡量价格波动水平",
        "source_url": None,
    },
    {
        "seq": 10, "code": "amp20", "name": "20日平均振幅",
        "category": "volatility",
        "formula": "MA((high - low) / preclose * 100, 20)",
        "description": "20 日平均日内振幅（%），(最高-最低)/前收",
        "source_url": None,
    },
    {
        "seq": 11, "code": "rsi14", "name": "RSI14 相对强弱",
        "category": "momentum",
        "formula": "SUM(IF(pct_chg > 0, pct_chg, 0), 14) / SUM(ABS(pct_chg), 14) * 100",
        "description": "14 日相对强弱指标：上涨幅度总和 / 总波动幅度 * 100",
        "source_url": None,
    },
    {
        "seq": 12, "code": "alpha101_006", "name": "Alpha101#006 开盘价量相关",
        "category": "volume",
        "formula": "0 - CORR(open, volume, 10)",
        "description": "WorldQuant Alpha101 第 6 式：开盘价与成交量 10 日相关性的负值",
        "source_url": _ALPHA101_URL,
    },
    {
        "seq": 13, "code": "alpha101_012", "name": "Alpha101#012 量增价跌",
        "category": "volume",
        "formula": "SIGN(DELTA(volume, 1)) * (0 - DELTA(close, 1))",
        "description": "WorldQuant Alpha101 第 12 式：成交量变动符号 × 价格反向变动",
        "source_url": _ALPHA101_URL,
    },
    {
        "seq": 14, "code": "alpha101_101", "name": "Alpha101#101 日内强弱",
        "category": "price",
        "formula": "(close - open) / (high - low + 0.001)",
        "description": "WorldQuant Alpha101 第 101 式：收盘相对开盘的日内位置强度",
        "source_url": _ALPHA101_URL,
    },
    {
        "seq": 15, "code": "vol_price_corr20", "name": "20日量价相关性",
        "category": "volume",
        "formula": "CORR(close, volume, 20)",
        "description": "收盘价与成交量 20 日相关系数，量价背离识别",
        "source_url": None,
    },
    {
        "seq": 16, "code": "vwap_dev", "name": "VWAP 偏离率",
        "category": "price",
        "formula": "(close - vwap) / vwap * 100",
        "description": "收盘价相对当日均价（成交额/成交量）的偏离百分比",
        "source_url": None,
    },
    {
        "seq": 17, "code": "high20_dev", "name": "距20日高点幅度",
        "category": "momentum",
        "formula": "(close / MAX(high, 20) - 1) * 100",
        "description": "收盘价距 20 日最高价的回撤幅度（%），越接近 0 越强",
        "source_url": None,
    },
]


_FACTOR_TABLE = sa.table(
    'business_factor',
    sa.column('id', sa.BigInteger),
    sa.column('deleted_at', sa.DateTime),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
    sa.column('name', sa.String),
    sa.column('code', sa.String),
    sa.column('formula', sa.Text),
    sa.column('category', sa.String),
    sa.column('description', sa.String),
    sa.column('source', sa.String),
    sa.column('source_url', sa.String),
    sa.column('params', sa.JSON),
    sa.column('status', sa.Boolean),
)


def upgrade() -> None:
    # ================================================================
    # 1. 因子库表
    # ================================================================
    op.create_table(
        'business_factor',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='因子名称'),
        sa.Column('code', sa.String(length=50), nullable=False,
                  comment='因子编码（唯一），如 alpha101_006/bias20'),
        sa.Column('formula', sa.Text(), nullable=False, comment='因子公式（DSL，安全求值器解析）'),
        sa.Column('category', sa.String(length=30), nullable=False,
                  comment='因子分类：momentum-动量，volume-量价，price-价格，volatility-波动，custom-自定义'),
        sa.Column('description', sa.String(length=500), nullable=True, comment='因子描述'),
        sa.Column('source', sa.String(length=20), nullable=False,
                  comment='来源：preset-预置开源因子库，imported-在线导入，custom-手工自建'),
        sa.Column('source_url', sa.String(length=500), nullable=True,
                  comment='来源链接（论文/研报/开源仓库）'),
        sa.Column('params', sa.JSON(), nullable=True, comment='预留参数化配置（JSON，暂不使用）'),
        sa.Column('status', sa.Boolean(), nullable=False, comment='状态：True-启用，False-停用'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True,
                  comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        comment='因子库表',
    )
    op.create_index(op.f('ix_business_factor_id'), 'business_factor', ['id'], unique=True)
    op.create_index('ix_factor_category', 'business_factor', ['category'], unique=False)
    op.create_index('ix_factor_source', 'business_factor', ['source'], unique=False)

    # ================================================================
    # 2. 幂等插入 17 条预置因子（按 code 查重，默认启用）
    # ================================================================
    conn = op.get_bind()
    existing_codes = {
        row[0] for row in conn.execute(
            sa.text("SELECT code FROM business_factor WHERE deleted_at IS NULL")
        )
    }
    rows = []
    for item in _PRESET_FACTORS:
        if item['code'] in existing_codes:
            continue
        # 注意：所有行必须带相同键集合（多行 INSERT 按首行键编译列清单），
        # 无可选值时置 None，插入后再统一清理为 SQL NULL
        rows.append({
            'id': _PRESET_ID_BASE + item['seq'],
            'deleted_at': None,
            'created_at': _DT,
            'updated_at': None,
            'name': item['name'],
            'code': item['code'],
            'formula': item['formula'],
            'category': item['category'],
            'description': item['description'],
            'source': 'preset',
            'source_url': item['source_url'],
            'params': None,
            'status': True,
        })
    if rows:
        op.bulk_insert(_FACTOR_TABLE, rows)
        # JSON/字符串列的 None 在 JSON 列会落成 JSON null，统一清理为 SQL NULL
        op.execute(
            "UPDATE business_factor SET params = NULL "
            "WHERE params IS NOT NULL AND params::text = 'null'"
        )


def downgrade() -> None:
    # 删除预置因子种子
    ids = ', '.join(str(_PRESET_ID_BASE + item['seq']) for item in _PRESET_FACTORS)
    op.execute(f"DELETE FROM business_factor WHERE id IN ({ids})")

    op.drop_index('ix_factor_source', table_name='business_factor')
    op.drop_index('ix_factor_category', table_name='business_factor')
    op.drop_index(op.f('ix_business_factor_id'), table_name='business_factor')
    op.drop_table('business_factor')
