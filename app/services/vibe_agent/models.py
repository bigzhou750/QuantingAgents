from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class VibeTaskStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class VibeEventType(str, Enum):
    session_created = "session_created"
    message_created = "message_created"
    task_queued = "task_queued"
    worker_status = "worker_status"
    token = "token"
    tool_call = "tool_call"
    evidence = "evidence"
    react_summary = "react_summary"
    swarm_status = "swarm_status"
    task_status = "task_status"
    error = "error"
    llm_usage = "llm_usage"
    balance_update = "balance_update"
    balance_exhausted = "balance_exhausted"


class VibeSessionCreate(BaseModel):
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VibeSessionUpdate(BaseModel):
    title: Optional[str] = None
    archived: Optional[bool] = None


class VibeMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    idempotency_key: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VibeSession(BaseModel):
    session_id: str
    user_id: str
    username: str
    title: str
    status: str = "idle"
    archived: bool = False
    runtime_root: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VibeMessage(BaseModel):
    message_id: str
    session_id: str
    user_id: str
    role: str
    content: str
    task_id: Optional[str] = None
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VibeTask(BaseModel):
    task_id: str
    session_id: str
    user_id: str
    username: str
    status: VibeTaskStatus
    prompt: str
    progress: int = 0
    attempt: int = 1
    idempotency_key: str
    runtime_root: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class VibeEvent(BaseModel):
    event_id: str
    sequence: int
    event_type: VibeEventType
    session_id: str
    user_id: str
    task_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class VibeCommand(BaseModel):
    command_id: str
    command_type: str
    user_id: str
    username: str
    session_id: str
    task_id: str
    idempotency_key: str
    runtime_root: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class VibeTaskList(BaseModel):
    tasks: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int

