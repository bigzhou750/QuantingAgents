"""
Agent 评测平台数据模型

包含评测集、评测用例、评测运行、trial、评分结果等 MongoDB 文档模型。
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Annotated
from enum import Enum

from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from bson import ObjectId

from app.utils.timezone import now_tz


# ==================== ObjectId 处理 ====================

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

class DatasetStatus(str, Enum):
    """评测集状态"""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class RunStatus(str, Enum):
    """评测运行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrialStatus(str, Enum):
    """Trial 状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ScoreSource(str, Enum):
    """评分来源"""
    RULE_BASED = "rule_based"
    FINANCIAL = "financial"
    EVIDENCE = "evidence"
    TRACE = "trace"
    SAFETY = "safety"
    LLM_JUDGE = "llm_judge"
    HUMAN_REVIEW = "human_review"


# ==================== 评测集模型 ====================

class EvalCase(BaseModel):
    """评测用例"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    case_id: str = Field(..., description="用例唯一标识（版本内唯一）")
    name: str = Field(..., description="用例名称")
    description: str = Field(default="", description="用例描述")
    input: Dict[str, Any] = Field(..., description="输入数据")
    expected_output: Optional[Dict[str, Any]] = Field(default=None, description="期望输出")
    scoring_criteria: Dict[str, Any] = Field(default_factory=dict, description="评分标准")
    tags: List[str] = Field(default_factory=list, description="标签")
    difficulty: str = Field(default="medium", description="难度级别: easy/medium/hard")
    category: str = Field(default="general", description="类别")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class EvalDataset(BaseModel):
    """评测集"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    dataset_id: str = Field(..., description="数据集唯一标识")
    name: str = Field(..., description="数据集名称")
    description: str = Field(default="", description="数据集描述")
    version: str = Field(default="1.0.0", description="版本号")
    status: DatasetStatus = Field(default=DatasetStatus.DRAFT)
    cases: List[str] = Field(default_factory=list, description="关联的 case_id 列表")
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_by: str = Field(default="", description="创建者")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== 评测运行模型 ====================

class EvalRunConfig(BaseModel):
    """评测运行配置"""
    agent_config: Dict[str, Any] = Field(default_factory=dict, description="Agent 配置")
    timeout_seconds: int = Field(default=600, description="单个 trial 超时时间")
    max_retries: int = Field(default=0, description="最大重试次数")
    scorer_names: List[str] = Field(default_factory=list, description="指定评分器")
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外配置")


class EvalRun(BaseModel):
    """评测运行"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    run_id: str = Field(..., description="运行唯一标识")
    dataset_id: str = Field(..., description="关联的数据集 ID")
    dataset_version: str = Field(..., description="数据集版本")
    status: RunStatus = Field(default=RunStatus.PENDING)
    config: EvalRunConfig = Field(default_factory=EvalRunConfig)
    num_trials_per_case: int = Field(default=1, description="每个 case 的 trial 次数")
    total_cases: int = Field(default=0, description="总 case 数")
    completed_trials: int = Field(default=0, description="已完成的 trial 数")
    failed_trials: int = Field(default=0, description="失败的 trial 数")
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    created_by: str = Field(default="", description="创建者")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)
    error_message: Optional[str] = Field(default=None)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== Trial 模型 ====================

class EvalTrial(BaseModel):
    """评测 Trial"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    trial_id: str = Field(..., description="Trial 唯一标识")
    run_id: str = Field(..., description="关联的运行 ID")
    case_id: str = Field(..., description="关联的用例 ID")
    trial_index: int = Field(default=0, description="Trial 序号（从 0 开始）")
    status: TrialStatus = Field(default=TrialStatus.PENDING)
    input_data: Dict[str, Any] = Field(default_factory=dict, description="实际输入")
    output_data: Optional[Dict[str, Any]] = Field(default=None, description="实际输出")
    trace_ref: Optional[str] = Field(default=None, description="Trace 引用 ID")
    token_usage: Dict[str, int] = Field(default_factory=dict, description="Token 使用情况")
    latency_ms: int = Field(default=0, description="耗时（毫秒）")
    cost_usd: float = Field(default=0.0, description="成本（美元）")
    error_message: Optional[str] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== Trace 事件模型 ====================

class TraceEventDoc(BaseModel):
    """Trace 事件文档"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    event_id: str = Field(..., description="事件唯一标识")
    trial_id: str = Field(..., description="关联的 trial ID")
    event_type: str = Field(..., description="事件类型")
    sequence: int = Field(default=0, description="事件序号")
    timestamp: datetime = Field(default_factory=now_tz)
    data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")
    parent_event_id: Optional[str] = Field(default=None, description="父事件 ID")
    created_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== 评分结果模型 ====================

class EvalScore(BaseModel):
    """评分结果"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    score_id: str = Field(..., description="评分唯一标识")
    trial_id: str = Field(..., description="关联的 trial ID")
    score_name: str = Field(..., description="评分维度名称")
    score: float = Field(..., ge=0.0, le=1.0, description="分数（0-1）")
    passed: bool = Field(default=False, description="是否通过")
    reason: str = Field(default="", description="评分原因")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    source: ScoreSource = Field(..., description="评分来源")
    scorer_version: str = Field(default="1.0.0", description="评分器版本")
    evidence_refs: List[str] = Field(default_factory=list, description="证据引用")
    raw_output: Optional[Dict[str, Any]] = Field(default=None, description="原始输出（LLM judge 等）")
    human_reviewed: bool = Field(default=False, description="是否经过人工复核")
    reviewer: Optional[str] = Field(default=None, description="复核人")
    review_comment: Optional[str] = Field(default=None, description="复核意见")
    original_score: Optional[float] = Field(default=None, description="原始分数（被覆盖时保留）")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== Bad Case 模型 ====================

class BadCaseSource(str, Enum):
    """Bad Case 来源"""
    TRIAL_FAILURE = "trial_failure"
    HUMAN_REVIEW = "human_review"
    SAFETY_INTERCEPT = "safety_intercept"
    USER_FEEDBACK = "user_feedback"
    ONLINE_SAMPLING = "online_sampling"


class EvalBadCase(BaseModel):
    """Bad Case"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    bad_case_id: str = Field(..., description="Bad Case 唯一标识")
    source: BadCaseSource = Field(..., description="来源")
    source_trial_id: Optional[str] = Field(default=None, description="来源 trial ID")
    source_run_id: Optional[str] = Field(default=None, description="来源 run ID")
    input_data: Dict[str, Any] = Field(..., description="输入数据")
    output_data: Optional[Dict[str, Any]] = Field(default=None, description="输出数据")
    failure_reason: str = Field(default="", description="失败原因")
    risk_level: str = Field(default="medium", description="风险级别: low/medium/high/critical")
    tags: List[str] = Field(default_factory=list, description="标签")
    converted_to_case_id: Optional[str] = Field(default=None, description="转换为正式 case 的 ID")
    created_by: str = Field(default="", description="创建者")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
