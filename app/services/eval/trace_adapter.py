"""
Agent Trace 适配器

将 Vibe Agent runtime 的事件归一为标准 trace 事件模型，
支持 llm_call、tool_call、skill_route、skill_execute、swarm_step、
retrieval、memory_read、memory_write、evidence、final_report、error、safety_check。
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from app.core.database import get_mongo_db
from app.models.eval import TraceEventDoc
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class TraceEventType(str, Enum):
    """Trace 事件类型"""
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    SKILL_ROUTE = "skill_route"
    SKILL_EXECUTE = "skill_execute"
    SWARM_STEP = "swarm_step"
    RETRIEVAL = "retrieval"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    EVIDENCE = "evidence"
    FINAL_REPORT = "final_report"
    ERROR = "error"
    SAFETY_CHECK = "safety_check"
    LIFECYCLE = "lifecycle"
    STREAMING = "streaming"


# Vibe Agent runtime 事件类型到标准 trace 类型的映射
# 基于 vibe_agent_runtime/vendor/src/ 源码中实际 emit 的事件名整理
VIBE_EVENT_TYPE_MAPPING = {
    # === LLM 调用 ===
    "llm_call": TraceEventType.LLM_CALL,
    "llm_response": TraceEventType.LLM_CALL,
    "llm_usage": TraceEventType.LLM_CALL,

    # === 工具调用 ===
    "tool_use": TraceEventType.TOOL_CALL,
    "tool_call": TraceEventType.TOOL_CALL,
    "tool_result": TraceEventType.TOOL_CALL,
    "tool_progress": TraceEventType.TOOL_CALL,
    "tool_heartbeat": TraceEventType.TOOL_CALL,

    # === Skill ===
    "skill_route": TraceEventType.SKILL_ROUTE,
    "skill_execute": TraceEventType.SKILL_EXECUTE,

    # === Swarm ===
    "swarm": TraceEventType.SWARM_STEP,
    "swarm_step": TraceEventType.SWARM_STEP,
    "swarm.started": TraceEventType.SWARM_STEP,
    "swarm.event": TraceEventType.SWARM_STEP,

    # === 检索 / 证据 ===
    "retrieval": TraceEventType.RETRIEVAL,
    "search": TraceEventType.RETRIEVAL,
    "evidence": TraceEventType.EVIDENCE,
    "citation": TraceEventType.EVIDENCE,
    "goal.evidence": TraceEventType.EVIDENCE,

    # === Memory ===
    "memory_read": TraceEventType.MEMORY_READ,
    "memory_write": TraceEventType.MEMORY_WRITE,

    # === 最终报告 ===
    "final_report": TraceEventType.FINAL_REPORT,
    "report": TraceEventType.FINAL_REPORT,

    # === 错误 / 安全 ===
    "error": TraceEventType.ERROR,
    "exception": TraceEventType.ERROR,
    "mcp.warning": TraceEventType.ERROR,
    "safety_check": TraceEventType.SAFETY_CHECK,
    "safety": TraceEventType.SAFETY_CHECK,

    # === 生命周期事件（session/attempt 级别） ===
    "session.created": TraceEventType.LIFECYCLE,
    "session_cleared": TraceEventType.LIFECYCLE,
    "message.received": TraceEventType.LIFECYCLE,
    "attempt.created": TraceEventType.LIFECYCLE,
    "attempt.started": TraceEventType.LIFECYCLE,
    "attempt.completed": TraceEventType.LIFECYCLE,
    "attempt.cancelled": TraceEventType.LIFECYCLE,
    "attempt.failed": TraceEventType.LIFECYCLE,
    "heartbeat": TraceEventType.LIFECYCLE,

    # === 流式输出 ===
    "text_delta": TraceEventType.STREAMING,
    "reasoning_delta": TraceEventType.STREAMING,
    "thinking_done": TraceEventType.STREAMING,
    "stream_reset": TraceEventType.STREAMING,
    "compact": TraceEventType.STREAMING,

    # === Goal ===
    "goal.updated": TraceEventType.EVIDENCE,
    "goal.created": TraceEventType.EVIDENCE,

    # === Live trading ===
    "live.action": TraceEventType.LIFECYCLE,
    "live.halted": TraceEventType.LIFECYCLE,
    "live.resumed": TraceEventType.LIFECYCLE,
    "mandate.committed": TraceEventType.LIFECYCLE,

    # === Stall / 性能警告 ===
    "stall_warning": TraceEventType.ERROR,
    "stalled": TraceEventType.ERROR,
}


class TraceAdapter:
    """Trace 适配器"""

    COLLECTION_EVENTS = "eval_trace_events"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化适配器，创建索引"""
        if self._initialized:
            return

        logger.info("Initializing TraceAdapter")
        db = get_mongo_db()

        # 创建索引
        await db[self.COLLECTION_EVENTS].create_index("event_id", unique=True)
        await db[self.COLLECTION_EVENTS].create_index("trial_id")
        await db[self.COLLECTION_EVENTS].create_index([("trial_id", 1), ("sequence", 1)])
        await db[self.COLLECTION_EVENTS].create_index("event_type")
        await db[self.COLLECTION_EVENTS].create_index("timestamp")

        self._initialized = True
        logger.info("TraceAdapter initialized with indexes")

    def adapt_vibe_event(
        self,
        vibe_event: Dict[str, Any],
        trial_id: str,
        sequence: int,
    ) -> Optional[TraceEventDoc]:
        """将 Vibe Agent runtime 事件转换为标准 trace 事件文档"""
        event_type_str = vibe_event.get("type", "").lower()

        # 映射 Vibe 事件类型到标准类型
        event_type = VIBE_EVENT_TYPE_MAPPING.get(event_type_str)
        if not event_type:
            logger.info(f"Unmapped vibe event type: {event_type_str}, treating as lifecycle")
            # 未知类型归为生命周期事件，而非错误
            event_type = TraceEventType.LIFECYCLE

        # 解析时间戳
        timestamp = vibe_event.get("timestamp")
        if isinstance(timestamp, str):
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                ts = now_tz()
        elif isinstance(timestamp, (int, float)):
            ts = datetime.fromtimestamp(timestamp)
        else:
            ts = now_tz()

        # 提取事件数据
        data = vibe_event.get("data", {})
        if not isinstance(data, dict):
            data = {"raw": data}

        # 添加元数据
        data["_meta"] = {
            "original_type": event_type_str,
            "adapted_at": now_tz().isoformat(),
        }

        event_id = f"{trial_id}_{sequence:06d}"

        return TraceEventDoc(
            event_id=event_id,
            trial_id=trial_id,
            event_type=event_type.value,
            sequence=sequence,
            timestamp=ts,
            data=data,
            parent_event_id=vibe_event.get("parent_event_id"),
        )

    async def save_trace_events(
        self,
        events: List[TraceEventDoc],
    ) -> int:
        """批量保存 trace 事件到存储"""
        if not events:
            return 0

        db = get_mongo_db()
        docs = [e.model_dump(by_alias=True, exclude={"id"}) for e in events]

        # 使用 insert_many 并忽略重复键错误
        try:
            result = await db[self.COLLECTION_EVENTS].insert_many(docs, ordered=False)
            count = len(result.inserted_ids)
        except Exception as e:
            # 处理部分插入成功的情况
            logger.warning(f"Some trace events may have been skipped: {e}")
            count = len(docs)

        logger.debug(f"Saved {count} trace events")
        return count

    async def save_single_event(
        self,
        event: TraceEventDoc,
    ) -> bool:
        """保存单个 trace 事件"""
        db = get_mongo_db()
        doc = event.model_dump(by_alias=True, exclude={"id"})

        try:
            await db[self.COLLECTION_EVENTS].insert_one(doc)
            return True
        except Exception as e:
            logger.warning(f"Failed to save trace event {event.event_id}: {e}")
            return False

    async def get_trace_events(
        self,
        trial_id: str,
        cursor: Optional[int] = None,
        limit: int = 100,
        event_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """获取某个 trial 的 trace 事件"""
        db = get_mongo_db()

        query = {"trial_id": trial_id}
        if cursor is not None:
            query["sequence"] = {"$gt": cursor}
        if event_types:
            query["event_type"] = {"$in": event_types}

        cursor_obj = db[self.COLLECTION_EVENTS].find(query).sort("sequence", 1).limit(limit)
        results = []
        async for doc in cursor_obj:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def get_event_count(
        self,
        trial_id: str,
        event_type: Optional[str] = None,
    ) -> int:
        """获取某个 trial 的事件数量"""
        db = get_mongo_db()

        query = {"trial_id": trial_id}
        if event_type:
            query["event_type"] = event_type

        return await db[self.COLLECTION_EVENTS].count_documents(query)

    async def get_events_summary(
        self,
        trial_id: str,
    ) -> Dict[str, Any]:
        """获取某个 trial 的事件摘要统计"""
        db = get_mongo_db()

        pipeline = [
            {"$match": {"trial_id": trial_id}},
            {"$group": {
                "_id": "$event_type",
                "count": {"$sum": 1},
                "first_sequence": {"$min": "$sequence"},
                "last_sequence": {"$max": "$sequence"},
            }},
            {"$sort": {"first_sequence": 1}},
        ]

        summary = {}
        async for doc in db[self.COLLECTION_EVENTS].aggregate(pipeline):
            summary[doc["_id"]] = {
                "count": doc["count"],
                "first_sequence": doc["first_sequence"],
                "last_sequence": doc["last_sequence"],
            }

        total = await db[self.COLLECTION_EVENTS].count_documents({"trial_id": trial_id})
        return {
            "total_events": total,
            "by_type": summary,
        }

    async def delete_trial_events(self, trial_id: str) -> int:
        """删除某个 trial 的所有 trace 事件"""
        db = get_mongo_db()
        result = await db[self.COLLECTION_EVENTS].delete_many({"trial_id": trial_id})
        logger.info(f"Deleted {result.deleted_count} trace events for trial {trial_id}")
        return result.deleted_count


# 单例实例
trace_adapter = TraceAdapter()
