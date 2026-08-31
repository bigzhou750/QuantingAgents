"""
Agent 自进化闭环数据模型

包含 artifact 版本、候选提案、验证运行、审批记录和回执等 MongoDB 文档模型。
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Annotated
from enum import Enum

from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from bson import ObjectId

from app.utils.timezone import now_tz


# ==================== ObjectId 处理（复用 eval 模式） ====================

def validate_object_id(v: Any) -> ObjectId:
    """验证ObjectId"""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def serialize_object_id(v: ObjectId) -> str:
    """序列化ObjectId为字符串"""
    return str(v)


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(serialize_object_id, return_type=str),
]


# ==================== 枚举类型 ====================

class ArtifactType(str, Enum):
    """可自进化的资产类型"""
    SKILL = "skill"
    PROMPT = "prompt"
    POLICY = "policy"
    RUBRIC = "rubric"
    CASE = "case"


class ProposalStatus(str, Enum):
    """候选提案状态"""
    DRAFT = "draft"
    PENDING_VERIFY = "pending_verify"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROMOTED = "promoted"
    ROLLBACK = "rollback"
    STOPPED = "stopped"


class ApprovalAction(str, Enum):
    """审批动作"""
    APPROVE = "approve"
    REJECT = "reject"
    COMMENT = "comment"


class StopReason(str, Enum):
    """停止原因"""
    BUDGET_EXCEEDED = "budget_exceeded"
    REPEATED_FAILURES = "repeated_failures"
    SAFETY_REGRESSION = "safety_regression"
    GATE_FAILURE = "gate_failure"
    MANUAL = "manual"


class TriggerType(str, Enum):
    """触发器类型"""
    RUN_COMPLETED = "run_completed"
    REGRESSION = "regression"
    BAD_CASE_THRESHOLD = "bad_case_threshold"
    SCHEDULED = "scheduled"


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ArtifactVersionStatus(str, Enum):
    """Artifact 版本状态"""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"


# ==================== 数据模型 ====================

class ArtifactVersion(BaseModel):
    """Artifact 版本记录"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    artifact_id: str = Field(..., description="Artifact 唯一标识")
    artifact_type: ArtifactType = Field(..., description="资产类型")
    name: str = Field(..., description="人类可读名称")
    path: str = Field(default="", description="文件系统或逻辑路径")
    version: str = Field(default="1.0.0", description="语义化版本号")
    content_hash: str = Field(default="", description="内容 SHA256 哈希")
    content_snapshot: Dict[str, Any] = Field(default_factory=dict, description="该版本的冻结内容")
    owner: str = Field(default="system", description="创建者")
    status: ArtifactVersionStatus = Field(default=ArtifactVersionStatus.ACTIVE, description="版本状态")
    created_at: datetime = Field(default_factory=now_tz)
    superseded_by: Optional[str] = Field(default=None, description="替代版本号")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ArtifactRegistryEntry(BaseModel):
    """Artifact 注册表条目"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    artifact_id: str = Field(..., description="Artifact 唯一标识")
    artifact_type: ArtifactType = Field(..., description="资产类型")
    name: str = Field(..., description="人类可读名称")
    path: str = Field(default="", description="文件系统或逻辑路径")
    current_version: str = Field(default="1.0.0", description="当前生效版本")
    owner: str = Field(default="system", description="负责人")
    rollback_strategy: str = Field(default="previous_stable", description="回滚策略")
    allowlist_patterns: List[str] = Field(default_factory=list, description="允许修改的路径模式")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class Proposal(BaseModel):
    """候选变更提案"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    proposal_id: str = Field(..., description="提案唯一标识 prop_xxx")
    trigger_run_id: str = Field(default="", description="触发的评测 run ID")
    trigger_type: TriggerType = Field(..., description="触发器类型")
    target_artifact_id: str = Field(..., description="目标 artifact ID")
    target_artifact_type: ArtifactType = Field(..., description="目标 artifact 类型")
    diff: Dict[str, Any] = Field(default_factory=dict, description="候选变更描述")
    reason: str = Field(default="", description="变更原因")
    sample_failure_ids: List[str] = Field(default_factory=list, description="关联失败样本 ID")
    impact_estimate: Dict[str, Any] = Field(default_factory=dict, description="影响面评估")
    budget_estimate: Dict[str, Any] = Field(default_factory=dict, description="预算评估")
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="风险等级")
    rollback_strategy: str = Field(default="restore_previous_version", description="回滚方式")
    status: ProposalStatus = Field(default=ProposalStatus.DRAFT, description="提案状态")
    forbidden_target: bool = Field(default=False, description="是否为禁止修改的目标")
    created_by: str = Field(default="system", description="创建者")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class VerificationRun(BaseModel):
    """候选验证运行记录"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    verification_id: str = Field(..., description="验证唯一标识 vrf_xxx")
    proposal_id: str = Field(..., description="关联提案 ID")
    baseline_run_id: str = Field(default="", description="基线 run ID")
    candidate_run_id: str = Field(default="", description="候选 run ID")
    sandbox_path: str = Field(default="", description="sandbox 临时目录路径")
    comparison_result: Dict[str, Any] = Field(default_factory=dict, description="对比结果")
    status: str = Field(default="pending", description="验证状态（复用 RunStatus 值）")
    created_at: datetime = Field(default_factory=now_tz)
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ApprovalRecord(BaseModel):
    """审批记录（嵌入到 Receipt 中，也可独立存储）"""
    reviewer: str = Field(..., description="审批人")
    action: ApprovalAction = Field(..., description="审批动作")
    comment: str = Field(default="", description="审批意见")
    timestamp: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class EvolutionReceipt(BaseModel):
    """自进化回执——完整生命周期记录"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    receipt_id: str = Field(..., description="回执唯一标识 rcpt_xxx")
    proposal_id: str = Field(..., description="关联提案 ID")
    verification_id: str = Field(default="", description="关联验证 ID")
    approval_records: List[ApprovalRecord] = Field(default_factory=list, description="审批记录列表")
    final_action: str = Field(default="", description="最终动作: promoted/rejected/stopped")
    stop_reason: Optional[StopReason] = Field(default=None, description="停止原因")
    promoted_version: Optional[str] = Field(default=None, description="promote 后的新版本号")
    created_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class EvolutionEventLog(BaseModel):
    """自进化事件日志"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    event_type: str = Field(..., description="事件类型: proposal_created/verified/approved/promoted/rollback/stopped")
    proposal_id: str = Field(default="", description="关联提案 ID")
    artifact_id: str = Field(default="", description="关联 artifact ID")
    trigger_source: str = Field(default="", description="触发来源")
    actor: str = Field(default="system", description="操作者")
    detail: Dict[str, Any] = Field(default_factory=dict, description="事件详情")
    created_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
