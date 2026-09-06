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


class DatasetPurpose(str, Enum):
    """评测集分层用途"""
    GENERAL = "general"
    ONLINE_REGRESSION = "online_regression"
    REVIEW_QUEUE = "review_queue"
    DETECTOR_EVAL = "detector_eval"
    GOLDEN = "golden"


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


class ScoreStatus(str, Enum):
    """评分状态

    区分真实评分结果与跳过/未配置/错误状态，
    避免未启用的第三方评分器被误当成真实低分。
    """
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"               # 评分器已注册但本次运行未选择
    NOT_CONFIGURED = "not_configured"   # 评分器依赖未安装或未启用
    ERROR = "error"                     # 评分器执行出错
    UNSCORABLE = "unscorable"           # 缺少必要证据或输出，无法形成确定结论
    NOT_APPLICABLE = "not_applicable"   # 当前 case 不适用该评分维度


class ClaimVerdict(str, Enum):
    """Claim 证据判定结果"""
    SUPPORTED = "supported"
    WEAKLY_SUPPORTED = "weakly_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNSCORABLE = "unscorable"


class ClaimTruthLabel(str, Enum):
    """人工复核后的 Claim 真值。"""
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    EXCLUDED = "excluded"


class HallucinationType(str, Enum):
    """幻觉 Claim 的业务分类。"""
    ENTITY = "entity"
    NUMERIC = "numeric"
    SOURCE = "source"
    TEMPORAL = "temporal"
    CONTRADICTION = "contradiction"
    OTHER = "other"


# ==================== Claim 人工标注 ====================

class ClaimAnnotation(BaseModel):
    """Claim 的单个真值标注记录。"""
    annotation_id: str = Field(..., description="标注记录唯一标识")
    reviewer: str = Field(..., description="标注人")
    truth_label: ClaimTruthLabel = Field(..., description="真值标签")
    hallucination_type: Optional[HallucinationType] = Field(default=None, description="幻觉类型")
    evidence_refs: List[str] = Field(default_factory=list, description="结构化证据引用")
    comment: str = Field(default="", description="标注说明或依据")
    label_version: str = Field(..., description="标注版本")
    timestamp: datetime = Field(default_factory=now_tz, description="标注时间")


# ==================== Claim-Evidence 结构 ====================

class ClaimEvidence(BaseModel):
    """单条 claim 及其证据映射

    用于 grounding scorer 输出，把最终输出拆解为可验证的 claim，
    并为每条 claim 记录证据引用、证据片段、来源、trace 事件、判定结果和理由。
    """
    claim_id: str = Field(..., description="Claim 唯一标识")
    claim_text: str = Field(..., description="Claim 原文")
    verdict: ClaimVerdict = Field(default=ClaimVerdict.UNSUPPORTED, description="判定结果")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    reason: str = Field(default="", description="判定理由")
    evidence_snippet: Optional[str] = Field(default=None, description="证据片段原文")
    evidence_source: Optional[str] = Field(default=None, description="证据来源（如检索工具名、文档ID）")
    trace_event_id: Optional[str] = Field(default=None, description="关联的 trace 事件 ID")
    conflicting_evidence: Optional[str] = Field(default=None, description="冲突证据（仅 contradicted 时）")
    truth_label: Optional[ClaimTruthLabel] = Field(default=None, description="人工真值标签")
    truth_source: Optional[str] = Field(default=None, description="真值来源")
    hallucination_type: Optional[HallucinationType] = Field(default=None, description="幻觉类型")
    prediction_label: Optional[bool] = Field(default=None, description="系统预测是否为幻觉")
    prediction_reason: Optional[str] = Field(default=None, description="系统预测原因")
    label_version: Optional[str] = Field(default=None, description="标注版本")
    verification_method: Optional[str] = Field(default=None, description="判定方法，如 structured_numeric_check / lexical_only / entailment_judge")
    annotation_history: List[ClaimAnnotation] = Field(default_factory=list, description="人工标注历史记录")


# ==================== 运行快照结构 ====================

class RunSnapshot(BaseModel):
    """运行快照

    创建 run 时固化 dataset version、case 内容、scorer 配置、judge 配置和数据窗口，
    确保金融行情、新闻、财报等时变数据下复盘可靠。
    """
    dataset_version: str = Field(..., description="数据集版本")
    case_contents: Dict[str, Any] = Field(default_factory=dict, description="case_id -> case 内容快照")
    scorer_config: List[Dict[str, Any]] = Field(default_factory=list, description="评分器配置快照")
    judge_config: Dict[str, Any] = Field(default_factory=dict, description="Judge 配置快照")
    data_window: Optional[Dict[str, Any]] = Field(default=None, description="数据时间窗口")
    created_at: datetime = Field(default_factory=now_tz, description="快照创建时间")


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
    metadata: Dict[str, Any] = Field(default_factory=dict, description="回流来源和评测元数据")
    archived: bool = Field(default=False, description="是否已归档（软删除）")
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
    judge_model: str = Field(default="", description="Judge 使用的模型")
    rubric_version: str = Field(default="", description="Rubric 版本")
    rubric: Optional[Dict[str, Any]] = Field(default=None, description="Rubric 内容")
    low_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="低置信度阈值")
    review_strategy: str = Field(default="auto", description="复核策略: auto/manual/all")
    quality_pass_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="质量 pass 阈值")
    required_scorers: List[str] = Field(default_factory=list, description="质量 pass 必须通过的 scorer")
    data_window: Optional[Dict[str, Any]] = Field(default=None, description="数据时间窗口")
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
    snapshot: Optional[RunSnapshot] = Field(default=None, description="运行快照（case/scorer/judge/data_window）")
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
    case_snapshot: Optional[Dict[str, Any]] = Field(default=None, description="运行时 case 内容快照")
    snapshot_version: Optional[str] = Field(default=None, description="执行时使用的数据集快照版本")
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

class ReviewAuditEntry(BaseModel):
    """复核审计条目"""
    reviewer: str = Field(..., description="复核人")
    action: str = Field(..., description="动作: approve/reject/adjust_score/add_bad_case/reflow")
    old_score: Optional[float] = Field(default=None, description="变更前分数")
    new_score: Optional[float] = Field(default=None, description="变更后分数")
    comment: str = Field(default="", description="复核意见")
    timestamp: datetime = Field(default_factory=now_tz, description="操作时间")


class EvalScore(BaseModel):
    """评分结果"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    score_id: str = Field(..., description="评分唯一标识")
    trial_id: str = Field(..., description="关联的 trial ID")
    score_name: str = Field(..., description="评分维度名称")
    score: float = Field(..., ge=0.0, le=1.0, description="分数（0-1）")
    passed: bool = Field(default=False, description="是否通过")
    status: ScoreStatus = Field(default=ScoreStatus.PASSED, description="评分状态")
    reason: str = Field(default="", description="评分原因")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    source: ScoreSource = Field(..., description="评分来源")
    scorer_version: str = Field(default="1.0.0", description="评分器版本")
    evidence_refs: List[str] = Field(default_factory=list, description="证据引用")
    claims: List[ClaimEvidence] = Field(default_factory=list, description="Claim-Evidence 结构")
    raw_output: Optional[Dict[str, Any]] = Field(default=None, description="原始输出（LLM judge 等）")
    human_reviewed: bool = Field(default=False, description="是否经过人工复核")
    reviewer: Optional[str] = Field(default=None, description="复核人")
    review_comment: Optional[str] = Field(default=None, description="复核意见")
    review_action: Optional[str] = Field(default=None, description="复核动作: approve/reject/adjust_score/add_bad_case/reflow")
    review_audit_trail: List[ReviewAuditEntry] = Field(default_factory=list, description="复核审计轨迹")
    original_score: Optional[float] = Field(default=None, description="原始分数（被覆盖时保留）")
    export_metadata: Optional[Dict[str, Any]] = Field(default=None, description="导出元数据")
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


class FailureFamily(str, Enum):
    """线上 Bad Case 失败家族"""
    EXECUTION = "execution"
    TOOL_TRAJECTORY = "tool_trajectory"
    SAFETY_COMPLIANCE = "safety_compliance"
    EVIDENCE_HALLUCINATION = "evidence_hallucination"
    OUTPUT_QUALITY = "output_quality"
    USER_FEEDBACK = "user_feedback"
    OPERATIONAL = "operational"


class DetectionStatus(str, Enum):
    """自动检测生命周期状态"""
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ReviewStatus(str, Enum):
    """Bad Case 人工复核状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_CONFIRMED = "auto_confirmed"
    MANUAL = "manual"


class DetectionSignal(BaseModel):
    """单个自动检测信号"""
    signal_type: str = Field(..., description="信号类型")
    failure_family: Optional[FailureFamily] = Field(default=None, description="信号对应失败家族")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="信号分数")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="信号置信度")
    severity: str = Field(default="medium", description="严重级别: low/medium/high/critical")
    reason: str = Field(default="", description="信号判定原因")
    evidence_refs: List[str] = Field(default_factory=list, description="trace/score/session 引用")
    detector_name: str = Field(default="", description="检测器名称")
    detector_version: str = Field(default="1.0.0", description="检测器版本")


class BadCaseSourceContext(BaseModel):
    """Bad Case 线上来源上下文"""
    user_id_hash: str = Field(default="", description="脱敏用户标识")
    session_id: str = Field(default="", description="来源会话 ID")
    task_id: str = Field(default="", description="来源任务 ID")
    trace_id: str = Field(default="", description="来源 trace ID")
    data_window: Optional[Dict[str, Any]] = Field(default=None, description="数据时间窗口")
    artifact_versions: Dict[str, Any] = Field(default_factory=dict, description="运行时 artifact 版本")
    release_receipt_id: Optional[str] = Field(default=None, description="发布回执 ID")
    replayable: bool = Field(default=True, description="是否可完整回放")


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
    source_trace_id: Optional[str] = Field(default=None, description="来源 trace/session ID")
    release_receipt_id: Optional[str] = Field(default=None, description="来源发布回执")
    artifact_version: Optional[str] = Field(default=None, description="线上运行时 artifact 版本")
    failure_family: Optional[FailureFamily] = Field(default=None, description="失败家族")
    detection_signals: List[DetectionSignal] = Field(default_factory=list, description="自动检测信号列表")
    detection_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="自动判定置信度")
    detection_status: DetectionStatus = Field(default=DetectionStatus.CONFIRMED, description="检测生命周期状态")
    review_status: ReviewStatus = Field(default=ReviewStatus.MANUAL, description="复核状态")
    review_required: bool = Field(default=False, description="是否需要人工复核")
    reviewer: Optional[str] = Field(default=None, description="复核人")
    review_comment: Optional[str] = Field(default=None, description="复核意见")
    dedup_key: Optional[str] = Field(default=None, description="去重指纹")
    source_context: Optional[BadCaseSourceContext] = Field(default=None, description="线上来源上下文")
    reflow_status: str = Field(default="pending", description="回流状态: pending/converted/failed")
    occurrence_count: int = Field(default=1, ge=1, description="相同指纹出现次数")
    affected_versions: List[str] = Field(default_factory=list, description="受影响的 artifact 版本")
    truth_label: Optional[str] = Field(default=None, description="人工确认的真值标签")
    hallucination_type: Optional[str] = Field(default=None, description="幻觉类型")
    label_version: Optional[str] = Field(default=None, description="标签版本")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
