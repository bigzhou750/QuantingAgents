import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from app.core.database import get_mongo_db, get_redis_client
from app.core.config import settings
from app.models.operation_log import ActionType
from app.services.operation_log_service import log_operation
from vibe_agent_runtime import embedded_agent_runtime

from .models import (
    VibeCommand,
    VibeEvent,
    VibeEventType,
    VibeMessage,
    VibeMessageCreate,
    VibeSession,
    VibeSessionCreate,
    VibeSessionUpdate,
    VibeTask,
    VibeTaskStatus,
    new_id,
    utc_now,
)
from .paths import ensure_session_tree, session_runtime_root, vibe_runtime_base
from .protocol import encode_event_payload, session_event_channel

logger = logging.getLogger(__name__)


def api_response(data: Any, message: str = "success") -> Dict[str, Any]:
    return {"success": True, "data": data, "message": message}


class VibeAgentService:
    session_collection = "vibe_agent_sessions"
    message_collection = "vibe_agent_messages"
    task_collection = "vibe_agent_tasks"
    event_collection = "vibe_agent_events"

    def __init__(self) -> None:
        self._background_tasks: set[asyncio.Task] = set()

    async def ensure_indexes(self) -> None:
        db = get_mongo_db()
        await db[self.session_collection].create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
        await db[self.message_collection].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING)])
        await db[self.task_collection].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        await db[self.task_collection].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("idempotency_key", ASCENDING)], unique=True)
        await db[self.event_collection].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("sequence", ASCENDING)], unique=True)

    async def create_session(self, user: Dict[str, Any], payload: VibeSessionCreate) -> VibeSession:
        session_id = new_id("vibesess")
        now = utc_now()
        root = ensure_session_tree(user["id"], session_id)
        session = VibeSession(
            session_id=session_id,
            user_id=user["id"],
            username=user["username"],
            title=payload.title or "新的研究会话",
            runtime_root=str(root),
            created_at=now,
            updated_at=now,
            metadata=payload.metadata,
        )
        await get_mongo_db()[self.session_collection].insert_one(session.model_dump())
        await self.append_event(user["id"], session_id, VibeEventType.session_created, {"title": session.title})
        return session

    async def list_sessions(self, user_id: str, limit: int = 50, archived: bool = False) -> List[Dict[str, Any]]:
        cursor = get_mongo_db()[self.session_collection].find(
            {"user_id": user_id, "archived": archived},
            {"_id": 0},
        ).sort("updated_at", DESCENDING).limit(min(limit, 100))
        return await cursor.to_list(length=min(limit, 100))

    async def get_session(self, user_id: str, session_id: str) -> Dict[str, Any]:
        session = await get_mongo_db()[self.session_collection].find_one(
            {"user_id": user_id, "session_id": session_id},
            {"_id": 0},
        )
        if not session:
            raise HTTPException(status_code=404, detail="研究会话不存在")
        return session

    async def update_session(self, user_id: str, session_id: str, payload: VibeSessionUpdate) -> Dict[str, Any]:
        await self.get_session(user_id, session_id)
        patch: Dict[str, Any] = {"updated_at": utc_now()}
        if payload.title is not None:
            patch["title"] = payload.title
        if payload.archived is not None:
            patch["archived"] = payload.archived
        await get_mongo_db()[self.session_collection].update_one(
            {"user_id": user_id, "session_id": session_id},
            {"$set": patch},
        )
        return await self.get_session(user_id, session_id)

    async def delete_session(self, user_id: str, session_id: str) -> None:
        await self.get_session(user_id, session_id)
        await get_mongo_db()[self.session_collection].update_one(
            {"user_id": user_id, "session_id": session_id},
            {"$set": {"archived": True, "updated_at": utc_now()}},
        )

    async def list_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        await self.get_session(user_id, session_id)
        cursor = get_mongo_db()[self.message_collection].find(
            {"user_id": user_id, "session_id": session_id},
            {"_id": 0},
        ).sort("created_at", ASCENDING)
        return await cursor.to_list(length=500)

    async def create_message_task(self, user: Dict[str, Any], session_id: str, payload: VibeMessageCreate) -> Dict[str, Any]:
        session = await self.get_session(user["id"], session_id)
        now = utc_now()
        idempotency_key = payload.idempotency_key or new_id("idem")

        existing = await get_mongo_db()[self.task_collection].find_one(
            {"user_id": user["id"], "session_id": session_id, "idempotency_key": idempotency_key},
            {"_id": 0},
        )
        if existing:
            return existing

        message_id = new_id("msg")
        task_id = new_id("vibetask")
        root = ensure_session_tree(user["id"], session_id)
        message = VibeMessage(
            message_id=message_id,
            session_id=session_id,
            user_id=user["id"],
            role="user",
            content=payload.content,
            task_id=task_id,
            created_at=now,
            metadata=payload.metadata,
        )
        task = VibeTask(
            task_id=task_id,
            session_id=session_id,
            user_id=user["id"],
            username=user["username"],
            status=VibeTaskStatus.queued,
            prompt=payload.content,
            idempotency_key=idempotency_key,
            runtime_root=str(root),
            created_at=now,
            updated_at=now,
        )
        command = VibeCommand(
            command_id=new_id("cmd"),
            command_type="run_research",
            user_id=user["id"],
            username=user["username"],
            session_id=session_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            runtime_root=str(root),
            payload={
                "prompt": payload.content,
                "metadata": payload.metadata,
                "audit_context": self.audit_context(user, session_id, task_id),
            },
            created_at=now,
        )

        db = get_mongo_db()
        await db[self.message_collection].insert_one(message.model_dump())
        await db[self.task_collection].insert_one(task.model_dump())
        await db[self.session_collection].update_one(
            {"user_id": user["id"], "session_id": session_id},
            {"$set": {"status": "queued", "updated_at": now}},
        )
        await self.append_event(user["id"], session_id, VibeEventType.message_created, {"message": message.model_dump()}, task_id)
        await self.append_event(user["id"], session_id, VibeEventType.task_queued, {"task": task.model_dump()}, task_id)
        task_handle = asyncio.create_task(self._run_internal_task(command))
        self._background_tasks.add(task_handle)
        task_handle.add_done_callback(self._background_tasks.discard)
        return {**task.model_dump(), "session_title": session.get("title")}

    async def _run_internal_task(self, command: VibeCommand) -> None:
        await self.update_task_status(command.user_id, command.task_id, VibeTaskStatus.processing)
        try:
            runtime_task = asyncio.create_task(embedded_agent_runtime.run(
                session_id=command.session_id,
                task_id=command.task_id,
                prompt=str(command.payload.get("prompt") or ""),
                title=str(command.payload.get("title") or "QuantingAgents 研究"),
                user_id=command.user_id,
                username=command.username,
                sink=lambda event_type, payload: self.ingest_worker_event(
                    {
                        "event_type": event_type,
                        "user_id": command.user_id,
                        "session_id": command.session_id,
                        "task_id": command.task_id,
                        "payload": payload,
                    }
                ),
            ))
            try:
                result = await asyncio.wait_for(
                    asyncio.shield(runtime_task),
                    timeout=float(getattr(settings, "VIBE_AGENT_TASK_TIMEOUT_SECONDS", 900)),
                )
            except asyncio.TimeoutError as exc:
                logger.error(
                    "embedded Vibe runtime timed out for %s after %ss",
                    command.task_id,
                    getattr(settings, "VIBE_AGENT_TASK_TIMEOUT_SECONDS", 900),
                )
                # Ask AgentLoop to stop cooperatively before cancelling the
                # facade task. This releases the runtime lock and avoids
                # leaving the session permanently busy.
                await embedded_agent_runtime.cancel(command.session_id)
                if not runtime_task.done():
                    runtime_task.cancel()
                    try:
                        await asyncio.wait_for(runtime_task, timeout=5)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                raise RuntimeError("Agent 运行超时，任务已停止，请稍后重试") from exc
            content = str(result.get("content") or "").strip()
            if content:
                db = get_mongo_db()
                existing_reply = await db[self.message_collection].find_one(
                    {
                        "user_id": command.user_id,
                        "session_id": command.session_id,
                        "task_id": command.task_id,
                        "role": "assistant",
                    },
                    {"_id": 0, "message_id": 1},
                )
                if existing_reply is None:
                    assistant_message = VibeMessage(
                        message_id=new_id("msg"),
                        session_id=command.session_id,
                        user_id=command.user_id,
                        role="assistant",
                        content=content,
                        task_id=command.task_id,
                        created_at=utc_now(),
                        metadata={
                            "status": result.get("status"),
                            "reason": result.get("reason"),
                            "run_dir": result.get("run_dir"),
                            "tool_trail": result.get("tool_trail", []),
                            "metrics": result.get("metrics", {}),
                            "elapsed_ms": result.get("elapsed_ms"),
                        },
                    )
                    await db[self.message_collection].insert_one(assistant_message.model_dump())
                    await self.append_event(
                        command.user_id,
                        command.session_id,
                        VibeEventType.message_created,
                        {"message": assistant_message.model_dump()},
                        command.task_id,
                    )
            current = await self.get_task(command.user_id, command.task_id)
            if current.get("status") not in {
                VibeTaskStatus.completed.value,
                VibeTaskStatus.failed.value,
                VibeTaskStatus.cancelled.value,
            }:
                await self.update_task_status(
                    command.user_id,
                    command.task_id,
                    VibeTaskStatus.completed,
                )
        except asyncio.CancelledError:
            await self.update_task_status(
                command.user_id, command.task_id, VibeTaskStatus.cancelled
            )
            raise
        except Exception as exc:
            logger.exception("embedded Vibe runtime failed for %s", command.task_id)
            await self.update_task_status(
                command.user_id,
                command.task_id,
                VibeTaskStatus.failed,
                str(exc),
            )
            await self.ingest_worker_event(
                {
                    "event_type": "attempt.failed",
                    "user_id": command.user_id,
                    "session_id": command.session_id,
                    "task_id": command.task_id,
                    "payload": {"error": str(exc)},
                }
            )

    async def append_event(
        self,
        user_id: str,
        session_id: str,
        event_type: VibeEventType,
        payload: Dict[str, Any],
        task_id: Optional[str] = None,
    ) -> VibeEvent:
        db = get_mongo_db()
        counter = await db["vibe_agent_counters"].find_one_and_update(
            {"user_id": user_id, "session_id": session_id},
            {"$inc": {"sequence": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        event = VibeEvent(
            event_id=new_id("evt"),
            sequence=int(counter.get("sequence", 1)),
            event_type=event_type,
            session_id=session_id,
            user_id=user_id,
            task_id=task_id,
            payload=payload,
            created_at=utc_now(),
        )
        event_doc = event.model_dump()
        await db[self.event_collection].insert_one(event_doc)
        try:
            await get_redis_client().publish(session_event_channel(session_id), encode_event_payload(event_doc))
        except Exception:
            logger.debug("unable to publish Vibe event to Redis", exc_info=True)
        return event

    async def update_task_status(
        self,
        user_id: str,
        task_id: str,
        status: VibeTaskStatus,
        error_message: Optional[str] = None,
    ) -> None:
        patch: Dict[str, Any] = {"status": status.value, "updated_at": utc_now()}
        if status == VibeTaskStatus.processing:
            patch["started_at"] = utc_now()
        if status in {VibeTaskStatus.completed, VibeTaskStatus.failed, VibeTaskStatus.cancelled}:
            patch["finished_at"] = utc_now()
        if error_message:
            patch["error_message"] = error_message
        await get_mongo_db()[self.task_collection].update_one(
            {"user_id": user_id, "task_id": task_id},
            {"$set": patch},
        )

    async def get_task(self, user_id: str, task_id: str) -> Dict[str, Any]:
        task = await get_mongo_db()[self.task_collection].find_one({"user_id": user_id, "task_id": task_id}, {"_id": 0})
        if not task:
            raise HTTPException(status_code=404, detail="研究任务不存在")
        return self.task_center_row(task)

    async def list_tasks(self, user_id: str, status: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
        query: Dict[str, Any] = {"user_id": user_id}
        if status:
            query["status"] = status
        skip = max(page - 1, 0) * page_size
        db = get_mongo_db()
        total = await db[self.task_collection].count_documents(query)
        cursor = db[self.task_collection].find(query, {"_id": 0}).sort("created_at", DESCENDING).skip(skip).limit(page_size)
        tasks = [self.task_center_row(item) for item in await cursor.to_list(length=page_size)]
        return {"tasks": tasks, "total": total, "page": page, "page_size": page_size}

    async def cancel_task(self, user: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        task = await self.get_task(user["id"], task_id)
        if task["status"] in ("completed", "failed", "cancelled"):
            return task
        await self.update_task_status(user["id"], task_id, VibeTaskStatus.cancelled)
        await self.append_event(
            user["id"],
            task["session_id"],
            VibeEventType.task_status,
            {"task_id": task_id, "status": "cancelled"},
            task_id,
        )
        await embedded_agent_runtime.cancel(task["session_id"])
        return await self.get_task(user["id"], task_id)

    async def replay_events(self, user_id: str, session_id: str, after: int = 0) -> List[Dict[str, Any]]:
        await self.get_session(user_id, session_id)
        cursor = get_mongo_db()[self.event_collection].find(
            {"user_id": user_id, "session_id": session_id, "sequence": {"$gt": after}},
            {"_id": 0},
        ).sort("sequence", ASCENDING).limit(500)
        return await cursor.to_list(length=500)

    async def event_stream(self, user_id: str, session_id: str, after: int = 0) -> AsyncGenerator[str, None]:
        await self.get_session(user_id, session_id)
        for event in await self.replay_events(user_id, session_id, after):
            yield self.sse("event", event)

        redis = get_redis_client()
        pubsub = redis.pubsub()
        channel = session_event_channel(session_id)
        await pubsub.subscribe(channel)
        yield self.sse("connected", {"session_id": session_id})
        heartbeat_every = int(getattr(settings, "SSE_HEARTBEAT_INTERVAL_SECONDS", 10))
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    data = message.get("data")
                    if isinstance(data, str):
                        yield f"event: event\ndata: {data}\n\n"
                    else:
                        yield self.sse("event", json.loads(data.decode("utf-8")))
                else:
                    await asyncio.sleep(0.1)
                    yield self.sse("heartbeat", {"timestamp": datetime.now(timezone.utc).isoformat()})
                    await asyncio.sleep(max(heartbeat_every - 1, 1))
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    def sse(self, event_name: str, data: Dict[str, Any]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

    async def health(self) -> Dict[str, Any]:
        diagnostics = await asyncio.to_thread(embedded_agent_runtime.capabilities)
        return {
            "available": bool(diagnostics.get("available")),
            "status": "ready" if diagnostics.get("available") else "unavailable",
            "runtime_root": str(vibe_runtime_base()),
            "diagnostics": diagnostics,
        }

    async def capabilities(self) -> Dict[str, Any]:
        return await asyncio.to_thread(embedded_agent_runtime.capabilities)

    def task_center_row(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **task,
            "task_type": "vibe_agent",
            "task_source": "embedded_vibe_agent_runtime",
            "stock_code": "",
            "stock_name": "自然语言研究",
            "analysis_type": "natural_language_research",
            "start_time": task.get("started_at") or task.get("created_at"),
            "created_at": task.get("created_at"),
            "progress": task.get("progress", 0),
            "result_url": f"/research-agent?session_id={task.get('session_id', '')}",
        }

    @staticmethod
    def audit_context(user: Dict[str, Any], session_id: str, task_id: str) -> Dict[str, Any]:
        """Build the identity envelope carried into every Worker execution."""
        return {
            "user_id": str(user["id"]),
            "username": str(user.get("username") or ""),
            "session_id": session_id,
            "task_id": task_id,
            "roles": list(user.get("roles") or []),
            "is_admin": bool(user.get("is_admin", False)),
        }

    async def ingest_worker_event(self, event: Dict[str, Any]) -> None:
        """Persist and fan out a normalized event emitted by the embedded runtime."""
        user_id = str(event.get("user_id") or "")
        session_id = str(event.get("session_id") or "")
        task_id = event.get("task_id")
        if not user_id or not session_id:
            logger.warning("discarding unscoped Vibe worker event: %s", event)
            return

        raw_type = str(event.get("event_type") or "worker_status")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        incoming_audit = payload.get("audit_context")
        if not isinstance(incoming_audit, dict):
            incoming_audit = {}
        # The API-derived envelope is authoritative. Child payloads may add
        # tool metadata, but cannot change the owning user/session/task.
        trusted_audit = {
            **incoming_audit,
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
        }
        mapping = {
            "text_delta": VibeEventType.token,
            "tool_call": VibeEventType.tool_call,
            "tool_result": VibeEventType.tool_call,
            "evidence": VibeEventType.evidence,
            "react_summary": VibeEventType.react_summary,
            "swarm_status": VibeEventType.swarm_status,
            "goal.updated": VibeEventType.evidence,
            "attempt.started": VibeEventType.task_status,
            "attempt.completed": VibeEventType.task_status,
            "attempt.failed": VibeEventType.task_status,
            "attempt.cancelled": VibeEventType.task_status,
            "mcp.warning": VibeEventType.error,
        }
        event_type = mapping.get(raw_type, VibeEventType.worker_status)

        if raw_type == "text_delta":
            payload = {"text": payload.get("delta", ""), **payload}
        elif raw_type in {"tool_call", "tool_result"}:
            payload = {"phase": raw_type, **payload}
            payload.setdefault(
                "audit_context",
                trusted_audit,
            )
            payload["audit_context"] = trusted_audit
            try:
                await log_operation(
                    user_id=user_id,
                    username=str(payload["audit_context"].get("username") or user_id),
                    action_type=ActionType.AGENT_RESEARCH,
                    action=f"Agent {raw_type}",
                    details={
                        "task_id": task_id,
                        "session_id": session_id,
                        "tool": payload.get("name") or payload.get("tool"),
                        "phase": raw_type,
                        "audit_context": payload["audit_context"],
                    },
                    success=raw_type == "tool_call" or not bool(payload.get("error")),
                    error_message=str(payload.get("error")) if payload.get("error") else None,
                    session_id=session_id,
                )
            except Exception:
                logger.warning("failed to write Vibe tool audit log", exc_info=True)
        elif raw_type in {
            "attempt.started",
            "attempt.completed",
            "attempt.failed",
            "attempt.cancelled",
        }:
            status = {
                "attempt.started": VibeTaskStatus.processing,
                "attempt.completed": VibeTaskStatus.completed,
                "attempt.failed": VibeTaskStatus.failed,
                "attempt.cancelled": VibeTaskStatus.cancelled,
            }[raw_type]
            await self.update_task_status(
                user_id,
                task_id,
                status,
                payload.get("error") if status == VibeTaskStatus.failed else None,
            )
            payload = {"status": status.value, **payload}
        elif raw_type in {"evidence", "react_summary", "swarm_status", "goal.updated"}:
            payload = {"phase": raw_type, **payload}
        elif raw_type.startswith("attempt."):
            payload = {"phase": raw_type, **payload}

        await self.append_event(user_id, session_id, event_type, payload, task_id)


vibe_agent_service = VibeAgentService()
