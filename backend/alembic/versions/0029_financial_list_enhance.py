"""financial list enhance: industry column + stock meta backfill + config table

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-01

1. business_financial_interpretation 新增 industry 列（所属行业）
2. 存量回填：financial_report / financial_interpretation 的 stock_name、interpretation 的
   industry，均按 stock_code 取 business_research_report 最新一条非空值（DB 内完成）
3. 新建 business_financial_config 财报解读分析策略配置表（单行 prompt_template）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0029'
down_revision: Union[str, Sequence[str], None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 每股最新一条非空研报名称/行业（published_date 优先，回退 fetched_at）
_RESEARCH_LATEST = """
    SELECT DISTINCT ON (stock_code)
        stock_code, stock_name, industry
    FROM business_research_report
    WHERE deleted_at IS NULL AND stock_name IS NOT NULL AND stock_name != ''
    ORDER BY stock_code, published_date DESC NULLS LAST, fetched_at DESC
"""


def upgrade() -> None:
    # ================================================================
    # 1. interpretation 加 industry 列
    # ================================================================
    op.add_column(
        'business_financial_interpretation',
        sa.Column('industry', sa.String(length=50), nullable=True, comment='所属行业（研报表/东财个股信息）'),
    )

    conn = op.get_bind()

    # ================================================================
    # 2. 存量回填（研报表 DB 内取最新非空值）
    # ================================================================
    # 2a. interpretation.stock_name
    conn.execute(sa.text(f"""
        UPDATE business_financial_interpretation t
        SET stock_name = r.stock_name
        FROM ({_RESEARCH_LATEST}) r
        WHERE t.stock_code = r.stock_code
          AND (t.stock_name IS NULL OR t.stock_name = '')
    """))
    # 2b. interpretation.industry（研报 industry 可为 NULL，逐股取最新一条有 industry 的研报）
    conn.execute(sa.text("""
        UPDATE business_financial_interpretation t
        SET industry = r.industry
        FROM (
            SELECT DISTINCT ON (stock_code) stock_code, industry
            FROM business_research_report
            WHERE deleted_at IS NULL AND industry IS NOT NULL AND industry != ''
            ORDER BY stock_code, published_date DESC NULLS LAST, fetched_at DESC
        ) r
        WHERE t.stock_code = r.stock_code AND t.industry IS NULL
    """))
    # 2c. financial_report.stock_name（后续解读创建记录时继承）
    conn.execute(sa.text(f"""
        UPDATE business_financial_report t
        SET stock_name = r.stock_name
        FROM ({_RESEARCH_LATEST}) r
        WHERE t.stock_code = r.stock_code
          AND (t.stock_name IS NULL OR t.stock_name = '')
    """))

    # ================================================================
    # 3. 财报解读分析策略配置表（单行）
    # ================================================================
    op.create_table(
        'business_financial_config',
        sa.Column('id', sa.BigInteger(), nullable=False, comment='雪花算法主键 ID'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间，为空则未删除'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('prompt_template', sa.Text(), nullable=True, comment='分析策略定制提示词（关注面/风格/风控偏好等，空则使用默认策略）'),
        sa.PrimaryKeyConstraint('id'),
        comment='财报 AI 解读分析策略配置表',
    )
    op.create_index(op.f('ix_business_financial_config_id'), 'business_financial_config', ['id'], unique=True)


def downgrade() -> None:
    # 运行中的环境禁止 downgrade（会丢数据），仅保留结构定义
    op.drop_index(op.f('ix_business_financial_config_id'), table_name='business_financial_config')
    op.drop_table('business_financial_config')
    op.drop_column('business_financial_interpretation', 'industry')
