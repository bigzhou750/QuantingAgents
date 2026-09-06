"""
Agent 决策可解释与审计数据模型。

统一保存节点级决策记录、分层解释、解释校验结果、生产指标和人工复核记录。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.utils.timezone import now_tz


class DecisionStatus(str, Enum):
    """决策节点状态"""

    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    REQUIRES_REVIEW = "requires_review"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class ExplanationStatus(str, Enum):
    """解释一致性校验状态"""

    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    UNVERIFIABLE = "unverifiable"


class ReviewStatus(str, Enum):
    """决策人工复核状态"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ADJUSTED = "adjusted"


class CandidateOption(BaseModel):
    """单个候选选项"""

    option_id: str = Field(..., description="候选标识")
    label: str = Field(default="", description="候选名称")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="候选元数据")
    rejected_reason: Optional[str] = Field(default=None, description="未选原因")


class DecisionRecordDoc(BaseModel):
    """节点级结构化决策记录"""

    id: Optional[str] = Field(default=None, alias="_id")
    decision_id: str = Field(..., description="决策唯一标识")
    sequence: int = Field(default=0, ge=0, description="决策链内顺序号")
    decision_type: str = Field(default="agent", description="决策类型: agent/tool/graph")
    business_id: Optional[str] = Field(default=None, description="业务 ID")
    task_id: Optional[str] = Field(default=None, description="任务 ID")
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    user_id: Optional[str] = Field(default=None, description="用户 ID")
    scenario: str = Field(default="", description="决策场景")
    candidates: List[CandidateOption] = Field(default_factory=list, description="候选选项")
    selected_option: Optional[str] = Field(default=None, description="最终选中项")
    selection_reason: str = Field(default="", description="选择依据")
    conclusion: str = Field(default="", description="最终结论")
    evidence_ids: List[str] = Field(default_factory=list, description="关联证据 ID")
    parent_decision_id: Optional[str] = Field(default=None, description="父决策 ID")
    status: DecisionStatus = Field(default=DecisionStatus.CONFIRMED, description="决策状态")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    risk_level: str = Field(default="low", description="风险等级: low/medium/high/critical")
    model_version: Optional[str] = Field(default=None, description="模型或策略版本")
    strategy_version: Optional[str] = Field(default=None, description="策略版本")
    raw_reasoning_ref: Optional[str] = Field(default=None, description="受控原始推理引用")
    created_at: datetime = Field(default_factory=now_tz, description="产生时间")
    updated_at: datetime = Field(default_factory=now_tz, description="更新时间")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ExplanationLayer(BaseModel):
    """单个受众层解释"""

    text: str = Field(default="", description="解释文本")
    source: str = Field(default="explanation_service", description="解释来源")
    generated_at: datetime = Field(default_factory=now_tz, description="生成时间")


class LayeredExplanation(BaseModel):
    """开发者/业务/用户三层解释"""

    id: Optional[str] = Field(default=None, alias="_id")
    explanation_id: str = Field(..., description="解释唯一标识")
    business_id: Optional[str] = Field(default=None, description="业务 ID")
    task_id: Optional[str] = Field(default=None, description="任务 ID")
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    decision_id: Optional[str] = Field(default=None, description="关联决策 ID")
    developer: ExplanationLayer = Field(default_factory=ExplanationLayer, description="开发者解释")
    business: ExplanationLayer = Field(default_factory=ExplanationLayer, description="业务解释")
    user: ExplanationLayer = Field(default_factory=ExplanationLayer, description="用户解释")
    version: str = Field(default="1.0.0", description="解释版本")
    source: str = Field(default="explanation_service", description="生成来源")
    created_at: datetime = Field(default_factory=now_tz, description="生成时间")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ExplanationValidation(BaseModel):
    """解释一致性校验结果"""

    id: Optional[str] = Field(default=None, alias="_id")
    validation_id: str = Field(..., description="校验唯一标识")
    explanation_id: str = Field(..., description="关联解释 ID")
    business_id: Optional[str] = Field(default=None, description="业务 ID")
    task_id: Optional[str] = Field(default=None, description="任务 ID")
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    decision_id: Optional[str] = Field(default=None, description="关联决策 ID")
    status: ExplanationStatus = Field(default=ExplanationStatus.UNVERIFIABLE, description="校验状态")
    reason: str = Field(default="", description="校验原因")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="校验置信度")
    validator_version: str = Field(default="1.0.0", description="校验器版本")
    created_at: datetime = Field(default_factory=now_tz, description="校验时间")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class DecisionReview(BaseModel):
    """决策人工复核记录"""

    id: Optional[str] = Field(default=None, alias="_id")
    review_id: str = Field(..., description="复核唯一标识")
    business_id: Optional[str] = Field(default=None, description="业务 ID")
    task_id: Optional[str] = Field(default=None, description="任务 ID")
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    decision_id: Optional[str] = Field(default=None, description="关联决策 ID")
    status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="复核状态")
    reviewer: Optional[str] = Field(default=None, description="复核人")
    action: str = Field(default="", description="复核动作")
    reason: str = Field(default="", description="复核原因")
    created_at: datetime = Field(default_factory=now_tz, description="创建时间")
    updated_at: datetime = Field(default_factory=now_tz, description="更新时间")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ExplainabilityMetricDoc(BaseModel):
    """生产决策链指标窗口"""

    id: Optional[str] = Field(default=None, alias="_id")
    metric_id: str = Field(..., description="指标唯一标识")
    window_start: datetime = Field(default_factory=now_tz, description="窗口开始")
    window_end: datetime = Field(default_factory=now_tz, description="窗口结束")
    task_type: str = Field(default="", description="任务类型")
    model_version: Optional[str] = Field(default=None, description="模型版本")
    risk_level: str = Field(default="", description="风险等级")
    decision_nodes: int = Field(default=0, ge=0, description="决策节点总数")
    missing_decision_nodes: int = Field(default=0, ge=0, description="缺失决策节点数")
    consistent_count: int = Field(default=0, ge=0, description="解释一致数")
    inconsistent_count: int = Field(default=0, ge=0, description="解释不一致数")
    unverifiable_count: int = Field(default=0, ge=0, description="不可验证数")
    evidence_covered: int = Field(default=0, ge=0, description="有证据关联数")
    evidence_total: int = Field(default=0, ge=0, description="应关联证据数")
    audit_query_count: int = Field(default=0, ge=0, description="审计查询次数")
    audit_query_total_ms: int = Field(default=0, ge=0, description="审计查询总耗时")
    high_risk_pauses: int = Field(default=0, ge=0, description="高风险暂停次数")
    created_at: datetime = Field(default_factory=now_tz, description="写入时间")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
