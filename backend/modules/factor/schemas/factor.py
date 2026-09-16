#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
因子管理相关 Schema
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from core.exception.errors import CustomError, RequestError
from core.response.response_code import CustomErrorCode

# 因子来源常量
FACTOR_SOURCES = ("preset", "imported", "custom")

# 选股条件操作符
SCREEN_OPS = ("gt", "gte", "lt", "lte", "top_n")

# 单次计算/选股的股票池上限
MAX_UNIVERSE_SIZE = 500


def _check_date_format(v: str) -> str:
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise RequestError(msg=f"日期格式非法: {v}，应为 YYYY-MM-DD")
    return v


class FactorCreateRequest(BaseModel):
    """创建因子请求（手工自建，source 固定为 custom）"""

    name: str = Field(..., min_length=1, max_length=100, description="因子名称")
    code: str = Field(..., min_length=1, max_length=50, description="因子代码（全局唯一）")
    category: str = Field("custom", max_length=30, description="分类，如 price/momentum/volume/volatility")
    formula: str = Field(..., min_length=1, description="因子公式（DSL，见公式说明）")
    description: Optional[str] = Field(None, max_length=500, description="因子说明")
    source_url: Optional[str] = Field(None, max_length=500, description="来源链接")
    params: Optional[dict] = Field(None, description="额外参数（JSON）")
    status: bool = Field(True, description="是否启用")


class FactorUpdateRequest(BaseModel):
    """更新因子请求（code 不可改；全字段可选，仅更新传入字段）"""

    name: Optional[str] = Field(None, min_length=1, max_length=100, description="因子名称")
    category: Optional[str] = Field(None, max_length=30, description="分类")
    formula: Optional[str] = Field(None, min_length=1, description="因子公式（DSL）")
    description: Optional[str] = Field(None, max_length=500, description="因子说明")
    source_url: Optional[str] = Field(None, max_length=500, description="来源链接")
    params: Optional[dict] = Field(None, description="额外参数（JSON）")
    status: Optional[bool] = Field(None, description="是否启用（预置因子只能停用，不能删除）")


class FactorItem(BaseModel):
    """因子列表/详情项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    category: str
    formula: str
    description: Optional[str] = None
    source: str  # preset-预置，imported-导入，custom-自建
    source_url: Optional[str] = None
    params: Optional[dict] = None
    status: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FactorImportRequest(BaseModel):
    """在线导入因子请求：url 与 content 二选一

    因子 JSON 格式约定（数组或单个对象）：
    [{"name": "因子名称", "code": "唯一代码", "category": "分类(可选)",
      "formula": "DSL 公式", "description": "说明(可选)", "source_url": "来源链接(可选)"}]
    逐条校验公式合法性与 code 唯一性，冲突/非法条目跳过并在 errors 中报告
    """

    url: Optional[str] = Field(None, description="因子 JSON 的 URL（GET 获取，15s 超时）")
    content: Optional[str] = Field(None, description="直接粘贴的因子 JSON 文本")

    @model_validator(mode="after")
    def _check_one_source(self):
        if bool(self.url) == bool(self.content):
            raise RequestError(msg="url 与 content 必须且只能提供一个")
        return self


class FactorImportResult(BaseModel):
    """导入结果：imported-成功条数，skipped-跳过条数，errors-逐条失败原因"""

    imported: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class FactorCalcRequest(BaseModel):
    """因子计算请求：对给定股票池计算目标日因子值"""

    factor_id: int = Field(..., description="因子 ID")
    codes: list[str] = Field(..., min_length=1, max_length=MAX_UNIVERSE_SIZE, description="股票代码列表")
    end_date: Optional[str] = Field(None, description="目标日期 YYYY-MM-DD，默认今天（取之前最后一个交易日）")
    lookback: int = Field(120, ge=5, le=750, description="回看交易日数（用于窗口函数）")

    @field_validator("end_date")
    @classmethod
    def _check_end_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date_format(v) if v else v


class FactorValueItem(BaseModel):
    """单只股票因子值"""

    code: str
    value: float


class FactorCalcResponse(BaseModel):
    """因子计算结果"""

    factor_id: int
    factor_code: str
    end_date: str = Field(..., description="实际目标交易日")
    values: list[FactorValueItem]
    warnings: list[str] = Field(default_factory=list)


class ScreenCondition(BaseModel):
    """选股条件：op=top_n 时 value 为前 N 名（按因子值降序），其余为阈值比较"""

    factor_id: int = Field(..., description="因子 ID")
    op: Literal["gt", "gte", "lt", "lte", "top_n"] = Field(..., description="比较操作符")
    value: float = Field(..., description="阈值；top_n 时为取前 N 名（正整数）")


class FactorScreenRequest(BaseModel):
    """选股器请求：codes 与 strategy_id 二选一（策略时使用其股票池）；多条件 AND

    注意：不支持全市场选股，必须显式给出股票池
    """

    codes: Optional[list[str]] = Field(None, max_length=MAX_UNIVERSE_SIZE, description="股票代码列表")
    strategy_id: Optional[int] = Field(None, description="策略 ID（使用该策略的股票池）")
    conditions: list[ScreenCondition] = Field(..., min_length=1, max_length=10, description="选股条件（AND）")
    end_date: Optional[str] = Field(None, description="目标日期 YYYY-MM-DD，默认今天（取之前最后一个交易日）")
    lookback: int = Field(120, ge=5, le=750, description="回看交易日数（用于窗口函数）")

    @field_validator("end_date")
    @classmethod
    def _check_end_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date_format(v) if v else v

    @model_validator(mode="after")
    def _check_universe(self):
        if bool(self.codes) == bool(self.strategy_id):
            raise RequestError(msg="codes 与 strategy_id 必须且只能提供一个（不支持全市场选股）")
        return self


class ScreenMatchItem(BaseModel):
    """选股命中项：factor_values 键为因子 code，值为因子值（无法计算时为 None）"""

    code: str
    name: str = ""
    factor_values: dict[str, Optional[float]] = Field(default_factory=dict)


class FactorScreenResponse(BaseModel):
    """选股结果"""

    total: int
    end_date: str = Field(..., description="实际目标交易日")
    matched: list[ScreenMatchItem]
    warnings: list[str] = Field(default_factory=list)


class SavePoolRequest(BaseModel):
    """将选股结果保存为策略股票池（覆盖 strategy.stock_pool = {"codes": [...]}）"""

    strategy_id: int = Field(..., description="策略 ID")
    codes: list[str] = Field(..., max_length=MAX_UNIVERSE_SIZE, description="股票代码列表（覆盖式保存）")


class SavePoolResponse(BaseModel):
    """保存股票池结果"""

    strategy_id: int
    total: int
