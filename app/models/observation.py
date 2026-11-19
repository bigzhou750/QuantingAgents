"""
投资观察标的模型

观察标的是选股结果与自选股之间的中间层，保留来源链路（strategy_id/task_id/match_reasons），
支持复盘备注和学习闭环追踪。
"""

from datetime import datetime, timedelta
from typing import Optional, List, Any
from enum import Enum

from pydantic import BaseModel, Field

from app.models.personal_investment import PyObjectId
from app.utils.timezone import now_tz


class ObservationSource(str, Enum):
    """观察来源"""
    SCREENING = "screening"       # 策略选股
    MANUAL = "manual"             # 手动添加
    FAVORITES = "favorites"       # 从自选股导入
    NEWS = "news"                 # 新闻关注


class ObservationStatus(str, Enum):
    """观察状态"""
    ACTIVE = "active"             # 观察中
    REMOVED = "removed"           # 已移出（保留历史记录）
    REVIEWED = "reviewed"         # 已复盘


class ReviewTargetType(str, Enum):
    """复盘目标类型"""
    OBSERVATION = "observation"
    PAPER_POSITION = "paper_position"


class ObservationRecord(BaseModel):
    """观察标的记录"""
    observation_id: str = Field(default_factory=lambda: "")
    user_id: str
    stock_code: str
    stock_name: str = ""
    market: str = "CN"

    # 来源追踪
    source_type: str = ObservationSource.MANUAL.value
    source_strategy_id: Optional[str] = None
    source_task_id: Optional[str] = None
    match_reasons: List[str] = Field(default_factory=list)
    risk_warnings: List[str] = Field(default_factory=list)

    # 数据快照
    data_as_of: Optional[datetime] = None

    # 用户备注
    user_notes: str = ""
    review_interval_days: int = Field(default=7, ge=1, le=365)
    next_review_at: Optional[datetime] = None

    # 新闻闭环扩展字段（可选）
    news_event_id: Optional[str] = None
    analysis_id: Optional[str] = None
    verification_indicators: List[str] = Field(default_factory=list)
    check_windows: List[int] = Field(default_factory=lambda: [1, 3, 7])

    # 状态管理
    status: str = ObservationStatus.ACTIVE.value

    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    def to_doc(self) -> dict:
        """转换为 MongoDB 文档"""
        doc = self.model_dump()
        if not doc.get("observation_id"):
            from bson import ObjectId
            doc["observation_id"] = str(ObjectId())
        return doc


class ReviewNote(BaseModel):
    """复盘备注"""
    note_id: str = Field(default_factory=lambda: "")
    user_id: str
    target_type: str = ReviewTargetType.OBSERVATION.value
    target_id: str
    content: str
    created_at: datetime = Field(default_factory=now_tz)

    def to_doc(self) -> dict:
        """转换为 MongoDB 文档"""
        doc = self.model_dump()
        if not doc.get("note_id"):
            from bson import ObjectId
            doc["note_id"] = str(ObjectId())
        return doc


# ==================== 请求模型 ====================

class AddObservationRequest(BaseModel):
    """添加观察标的请求"""
    stock_code: str
    stock_name: str = ""
    market: str = "CN"
    source_type: str = ObservationSource.MANUAL.value
    source_strategy_id: Optional[str] = None
    source_task_id: Optional[str] = None
    match_reasons: List[str] = Field(default_factory=list)
    risk_warnings: List[str] = Field(default_factory=list)
    user_notes: str = ""
    data_as_of: Optional[datetime] = None
    review_interval_days: int = Field(default=7, ge=1, le=365)


class UpdateObservationRequest(BaseModel):
    """更新观察标的请求"""
    user_notes: Optional[str] = None
    status: Optional[str] = None
    review_interval_days: Optional[int] = Field(default=None, ge=1, le=365)


class AddReviewNoteRequest(BaseModel):
    """添加复盘备注请求"""
    content: str
    target_type: str = ReviewTargetType.OBSERVATION.value
