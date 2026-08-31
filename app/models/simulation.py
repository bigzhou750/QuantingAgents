"""
策略历史模拟数据模型

存储第一阶段策略模拟结果到 MongoDB。
"""

from datetime import datetime
from typing import Optional, Dict, Any, Annotated

from pydantic import BaseModel, Field
from bson import ObjectId

from app.utils.timezone import now_tz


def _validate_object_id(v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str) and ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def _serialize_object_id(v: ObjectId) -> str:
    return str(v)


PyObjectId = Annotated[
    ObjectId,
    Field(default=None),
]


class SimulationResultDoc(BaseModel):
    """策略模拟结果文档"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    result_id: str = Field(..., description="结果唯一标识")
    strategy_id: str = Field(..., description="关联策略或模板 ID")

    # 模拟配置快照
    config: Dict[str, Any] = Field(default_factory=dict, description="模拟参数快照")

    # 核心指标
    cumulative_return: float = Field(default=0.0, description="累计模拟收益率")
    annualized_return: float = Field(default=0.0, description="年化模拟收益率")
    max_drawdown: float = Field(default=0.0, description="最大回撤（负数）")
    sharpe_ratio: Optional[float] = Field(default=None, description="夏普比率")

    # 模拟区间
    simulation_start: str = Field(default="", description="模拟开始日期 YYYY-MM-DD")
    simulation_end: str = Field(default="", description="模拟结束日期 YYYY-MM-DD")

    # 样本与覆盖率
    sample_count: int = Field(default=0, ge=0, description="参与模拟的股票数量")
    coverage_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="数据覆盖率")

    # 数据质量
    data_as_of: Optional[datetime] = Field(default=None, description="数据截至时间")
    data_sufficient: bool = Field(default=True, description="数据是否充分")
    data_quality_note: Optional[str] = Field(default=None, description="数据质量说明")

    # 调仓次数
    rebalance_count: int = Field(default=0, ge=0, description="调仓次数")

    # 元数据
    created_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
