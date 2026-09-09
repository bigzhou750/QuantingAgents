"""按业务 ID 聚合 Agent 决策审计链的服务。"""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.core.database import get_mongo_db
from app.models.decision import ReviewStatus
from app.services.explainability.record_service import decision_record_store
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class DecisionAuditService:
    """聚合决策记录、trace、证据、最终输出、操作日志和复核记录。"""

    def __init__(self) -> None:
        self.store = decision_record_store

    async def _resolve_task(
        self, identifier: str
    ) -> Optional[Dict[str, Any]]:
        db = get_mongo_db()
        task = await db["vibe_agent_tasks"].find_one(
            {"task_id": identifier},
            {"_id": 0},
        )
        if task:
            return task
        task = await db["vibe_agent_tasks"].find_one(
            {"session_id": identifier},
            {"_id": 0},
        )
        if task:
            return task
        return None

    async def _assert_authorized(
        self,
        identifier: str,
        task: Optional[Dict[str, Any]],
        user: Dict[str, Any],
        records: List[Dict[str, Any]],
    ) -> None:
        if user.get("is_admin", False):
            return
        user_id = str(user.get("id") or "")
        if task and str(task.get("user_id") or "") == user_id:
            return
        if records and any(str(item.get("user_id") or "") == user_id for item in records):
            return
        db = get_mongo_db()
        session = await db["vibe_agent_sessions"].find_one(
            {
                "session_id": identifier,
                "user_id": user_id,
            },
            {"_id": 0},
        )
        if session:
            return
        raise HTTPException(status_code=403, detail="无权访问该决策审计链")

    async def build_audit(
        self,
        identifier: str,
        user: Dict[str, Any],
        scope: str = "auto",
    ) -> Dict[str, Any]:
        start = time.monotonic()
        db = get_mongo_db()
        scope = scope if scope in {"session", "task"} else "auto"
        task = await self._resolve_task(identifier) if scope != "session" else None
        if scope == "auto":
            scope = "task" if task and str(task.get("task_id")) == identifier else "session"

        if scope == "session":
            task_id: Optional[str] = None
            session_id = identifier
            records = await self.store.list_decision_records(session_id=session_id, limit=500)
            task_cursor = db["vibe_agent_tasks"].find(
                {"session_id": session_id}, {"_id": 0}
            ).sort("created_at", 1).limit(100)
            task_docs = await task_cursor.to_list(length=100)
        else:
            task_id = str(task.get("task_id") or identifier) if task else identifier
            session_id = str(task.get("session_id") or "") if task else ""
            records = await self.store.list_decision_records(task_id=task_id, limit=200)
            task_docs = [task] if task else []
        await self._assert_authorized(identifier, task, user, records)

        trace_query: Dict[str, Any] = {"$or": []}
        if scope == "session":
            trace_query["$or"].append({"session_id": session_id})
        else:
            trace_query["$or"].extend(
                [{"trial_id": identifier}, {"task_id": task_id}, {"business_id": identifier}]
            )
        if not trace_query["$or"]:
            trace_query = {}
        trace_cursor = db["eval_trace_events"].find(trace_query).sort("sequence", 1).limit(1000)
        trace_events: List[Dict[str, Any]] = []
        async for doc in trace_cursor:
            doc["id"] = str(doc.pop("_id"))
            trace_events.append(doc)

        event_query: Dict[str, Any]
        if scope == "session":
            event_query = {"session_id": session_id}
        else:
            event_query = {"task_id": task_id}
        vibe_events: List[Dict[str, Any]] = []
        if event_query:
            event_cursor = db["vibe_agent_events"].find(event_query).sort("sequence", 1).limit(1000)
            async for doc in event_cursor:
                doc["id"] = str(doc.pop("_id"))
                vibe_events.append(doc)

        op_query: Dict[str, Any] = {}
        if scope == "session":
            op_query = {"session_id": session_id}
        elif task_id and task_id != identifier:
            op_query["details.task_id"] = task_id
        elif session_id and session_id != identifier:
            op_query["session_id"] = session_id
        else:
            op_query = {"$or": [{"details.task_id": identifier}, {"details.session_id": identifier}]}
        op_cursor = db["operation_logs"].find(op_query).sort("timestamp", -1).limit(200)
        operation_logs: List[Dict[str, Any]] = []
        async for doc in op_cursor:
            doc["id"] = str(doc.pop("_id"))
            operation_logs.append(doc)

        final_output = ""
        message_query: Dict[str, Any] = {"role": "assistant"}
        if scope == "session":
            message_query["session_id"] = session_id
        elif task_id:
            message_query["task_id"] = task_id
        if message_query:
            message = await db["vibe_agent_messages"].find_one(
                message_query,
                {"_id": 0, "content": 1},
                sort=[("created_at", -1)],
            )
            if message:
                final_output = str(message.get("content") or "")
        if not final_output:
            trial = await db["eval_trials"].find_one(
                {"trial_id": identifier},
                {"_id": 0, "output_data": 1},
            )
            if trial:
                output = trial.get("output_data") or {}
                final_output = str(output.get("content") or output.get("result") or "")

        message_query: Dict[str, Any] = {"role": {"$in": ["user", "assistant"]}}
        if scope == "session":
            message_query["session_id"] = session_id
        else:
            message_query["task_id"] = task_id
        message_cursor = db["vibe_agent_messages"].find(
            message_query, {"_id": 0}
        ).sort("created_at", 1).limit(500)
        messages: List[Dict[str, Any]] = await message_cursor.to_list(length=500)

        lookup_task_id = task_id or identifier
        if scope == "session":
            task_ids = [str(item.get("task_id") or "") for item in task_docs]
            explanations: List[Dict[str, Any]] = []
            validations: List[Dict[str, Any]] = []
            reviews: List[Dict[str, Any]] = []
            for item_task_id in filter(None, task_ids):
                explanations.extend(await self.store.list_explanations(task_id=item_task_id))
                validations.extend(await self.store.list_validations(task_id=item_task_id))
                reviews.extend(await self.store.list_reviews(task_id=item_task_id))
        else:
            explanations = await self.store.list_explanations(task_id=lookup_task_id)
            validations = await self.store.list_validations(task_id=lookup_task_id)
            reviews = await self.store.list_reviews(task_id=lookup_task_id)
        latency_ms = int((time.monotonic() - start) * 1000)

        evidence_events = [
            event for event in trace_events
            if event.get("event_type") in {"evidence", "retrieval", "citation"}
        ]
        if not records and (trace_events or vibe_events or operation_logs):
            audit_status = "legacy_unverified"
        elif not records and not trace_events and not vibe_events:
            audit_status = "unavailable"
        else:
            audit_status = "complete"

        return {
            "business_id": identifier,
            "scope": scope,
            "task_id": task_id,
            "session_id": session_id,
            "audit_status": audit_status,
            "tasks": task_docs,
            "messages": messages,
            "decision_chain": records,
            "trace_events": trace_events,
            "vibe_events": vibe_events,
            "evidence_events": evidence_events,
            "final_output": final_output,
            "operation_logs": operation_logs,
            "explanations": explanations,
            "validations": validations,
            "reviews": reviews,
            "query_latency_ms": latency_ms,
        }

    async def update_review_status(
        self,
        review_id: str,
        reviewer: str,
        action: str,
        reason: str,
    ) -> Optional[Dict[str, Any]]:
        db = get_mongo_db()
        review = await db[self.store.REVIEWS].find_one({"review_id": review_id})
        if not review:
            return None
        mapped = {
            "approve": ReviewStatus.APPROVED,
            "reject": ReviewStatus.REJECTED,
            "adjust": ReviewStatus.ADJUSTED,
        }
        status = mapped.get(action, ReviewStatus.APPROVED).value
        await db[self.store.REVIEWS].update_one(
            {"review_id": review_id},
            {
                "$set": {
                    "status": status,
                    "reviewer": reviewer,
                    "action": action,
                    "reason": reason,
                    "updated_at": now_tz(),
                }
            },
        )
        review["status"] = status
        review["reviewer"] = reviewer
        review["action"] = action
        review["reason"] = reason
        return review


decision_audit_service = DecisionAuditService()
