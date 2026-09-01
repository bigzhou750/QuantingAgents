"""
新闻智能闭环数据模型

覆盖新闻聚合、Agent分析、持仓影响、告警状态机和复盘验证。
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.utils.timezone import now_tz


# ==================== 枚举 ====================

class NewsSourceStatus(str, Enum):
    """新闻来源状态"""
    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"


class AlertAction(str, Enum):
    """告警用户动作"""
    CONFIRM = "confirm"
    IGNORE = "ignore"
    CONVERT = "convert"
    REVIEW = "review"


class AlertStatus(str, Enum):
    """告警状态"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"
    CONVERTED = "converted"
    REVIEWED = "reviewed"


class ReviewVerdict(str, Enum):
    """复盘判定"""
    VERIFIED = "verified"         # 预测方向与实际一致
    UNVERIFIED = "unverified"     # 无法确认
    CONTRADICTED = "contradicted" # 预测方向与实际相反


# ==================== 数据类 ====================

@dataclass
class SourceStatusEntry:
    """单个来源的状态"""
    source_name: str
    status: str  # NewsSourceStatus value
    count: int = 0
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None


@dataclass
class AggregatedNewsResult:
    """聚合新闻结果"""
    news_list: List[Dict[str, Any]] = field(default_factory=list)
    event_clusters: List[Dict[str, Any]] = field(default_factory=list)
    source_statuses: List[Dict[str, Any]] = field(default_factory=list)
    fallback_steps: List[str] = field(default_factory=list)
    direct_count: int = 0
    indirect_count: int = 0
    freshness: Optional[str] = None  # ISO datetime of newest item
    failure_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "news_list": self.news_list,
            "event_clusters": self.event_clusters,
            "source_statuses": self.source_statuses,
            "fallback_steps": self.fallback_steps,
            "direct_count": self.direct_count,
            "indirect_count": self.indirect_count,
            "freshness": self.freshness,
            "failure_summary": self.failure_summary,
        }


# Agent 分析输出 schema (17字段)
ANALYSIS_SCHEMA_FIELDS = [
    "event_summary",
    "event_type",
    "impact_direction",       # positive / negative / neutral
    "impact_strength",        # 1-5
    "time_horizon",           # short / medium / long
    "affected_industries",
    "affected_concepts",
    "upstream_downstream_paths",
    "direct_symbols",
    "indirect_symbols",
    "portfolio_hits",
    "impact_paths",
    "evidence_strength",      # strong / moderate / weak
    "market_confirmation",
    "watch_indicators",
    "uncertainties",
    "non_advisory_note",
]


@dataclass
class NewsAnalysisRecord:
    """Agent 分析记录"""
    analysis_id: str = ""
    news_ids: List[str] = field(default_factory=list)
    prompt_version: str = "v1"
    schema_version: str = "v1"
    model_config: str = "qwen-plus"
    result: Dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_doc(self) -> Dict[str, Any]:
        if not self.analysis_id:
            from bson import ObjectId
            self.analysis_id = str(ObjectId())
        if not self.created_at:
            self.created_at = now_tz()
        return {
            "analysis_id": self.analysis_id,
            "news_ids": self.news_ids,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "model_config": self.model_config,
            "result": self.result,
            "degraded": self.degraded,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at,
        }


@dataclass
class HoldingImpactCard:
    """持仓影响评分卡"""
    stock_code: str
    stock_name: str = ""
    direction: str = "neutral"          # positive / negative / neutral
    strength: int = 0                   # 1-5
    exposure: float = 0.0               # 仓位占比
    news_count: int = 0
    freshness: Optional[str] = None
    evidence_quality: str = "weak"      # strong / moderate / weak
    market_confirmation: str = ""
    risk_category: str = ""
    watch_indicators: List[str] = field(default_factory=list)
    is_direct: bool = True              # 直接 vs 间接影响
    impact_paths: List[str] = field(default_factory=list)
    analysis_id: Optional[str] = None   # 关联的分析记录
    refresh_state: str = "current"      # current / refreshing / insufficient / source_failure

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "direction": self.direction,
            "strength": self.strength,
            "exposure": self.exposure,
            "news_count": self.news_count,
            "freshness": self.freshness,
            "evidence_quality": self.evidence_quality,
            "market_confirmation": self.market_confirmation,
            "risk_category": self.risk_category,
            "watch_indicators": self.watch_indicators,
            "is_direct": self.is_direct,
            "impact_paths": self.impact_paths,
            "analysis_id": self.analysis_id,
            "refresh_state": self.refresh_state,
        }


@dataclass
class ClosedLoopMetrics:
    """闭环指标"""
    coverage_rate: float = 0.0          # 新闻覆盖率
    analysis_success_rate: float = 0.0  # 分析成功率
    alert_hit_rate: float = 0.0         # 告警命中率
    task_completion_rate: float = 0.0   # 观察任务完成率
    review_verification_rate: float = 0.0  # 复盘验证率
    noise_rate: float = 0.0             # 噪声率(被忽略/失效的比例)
    total_news: int = 0
    total_analyses: int = 0
    total_alerts: int = 0
    total_tasks: int = 0
    total_reviews: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coverage_rate": round(self.coverage_rate, 3),
            "analysis_success_rate": round(self.analysis_success_rate, 3),
            "alert_hit_rate": round(self.alert_hit_rate, 3),
            "task_completion_rate": round(self.task_completion_rate, 3),
            "review_verification_rate": round(self.review_verification_rate, 3),
            "noise_rate": round(self.noise_rate, 3),
            "total_news": self.total_news,
            "total_analyses": self.total_analyses,
            "total_alerts": self.total_alerts,
            "total_tasks": self.total_tasks,
            "total_reviews": self.total_reviews,
        }


# ==================== 请求模型 ====================

class AnalyzeNewsRequest(BaseModel):
    """单条新闻分析请求"""
    news_id: Optional[str] = None
    title: str = ""
    content: str = ""
    source: str = ""
    published_at: Optional[str] = None
    symbol: Optional[str] = None


class AnalyzeBatchRequest(BaseModel):
    """批量新闻分析请求"""
    news_items: List[AnalyzeNewsRequest] = Field(default_factory=list)
    cluster_first: bool = True  # 先聚类再分析


class AlertStatusUpdateRequest(BaseModel):
    """告警状态更新请求"""
    action: str  # confirm / ignore / convert / review
    note: str = ""


class ObservationFromNewsRequest(BaseModel):
    """从新闻创建观察任务请求"""
    stock_code: str
    stock_name: str = ""
    news_event_id: Optional[str] = None
    analysis_id: Optional[str] = None
    verification_indicators: List[str] = Field(default_factory=list)
    user_notes: str = ""
