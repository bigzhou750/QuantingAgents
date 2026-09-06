import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
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
from .paths import ensure_session_tree, session_runtime_root, vibe_runtime_base, assert_within_user_scope
from .protocol import encode_event_payload, session_event_channel

# 个人投资助手上下文注入（可选）
try:
    from app.services.personal_investment.context_builder import ContextBuilder
    HAS_CONTEXT_BUILDER = True
except ImportError:
    HAS_CONTEXT_BUILDER = False
    ContextBuilder = None

logger = logging.getLogger(__name__)


def api_response(data: Any, message: str = "success") -> Dict[str, Any]:
    return {"success": True, "data": data, "message": message}


class VibeAgentService:
    session_collection = "vibe_agent_sessions"
    message_collection = "vibe_agent_messages"
    task_collection = "vibe_agent_tasks"
    event_collection = "vibe_agent_events"
    feedback_collection = "vibe_agent_feedback"

    def __init__(self) -> None:
        self._background_tasks: set[asyncio.Task] = set()
        self._message_submit_lock = asyncio.Lock()

    async def ensure_indexes(self) -> None:
        db = get_mongo_db()
        await db[self.session_collection].create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
        await db[self.message_collection].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING)])
        await db[self.task_collection].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        await db[self.task_collection].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("idempotency_key", ASCENDING)], unique=True)
        await db[self.event_collection].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("sequence", ASCENDING)], unique=True)
        await db[self.feedback_collection].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("task_id", ASCENDING)])
        await self.recover_orphaned_tasks()

    async def recover_orphaned_tasks(self) -> None:
        """Release tasks left active when the API process was restarted."""
        cursor = get_mongo_db()[self.task_collection].find(
            {
                "status": {
                    "$in": [
                        VibeTaskStatus.queued.value,
                        VibeTaskStatus.processing.value,
                    ]
                }
            },
            {"_id": 0, "user_id": 1, "session_id": 1, "task_id": 1},
        )
        orphaned = await cursor.to_list(length=1000)
        for task in orphaned:
            message = "服务重启时任务尚未完成，已停止本次执行，请重新发起研究。"
            await self.update_task_status(
                str(task["user_id"]),
                str(task["task_id"]),
                VibeTaskStatus.failed,
                message,
            )
            await self.append_event(
                str(task["user_id"]),
                str(task["session_id"]),
                VibeEventType.task_status,
                {"task_id": task["task_id"], "status": "failed", "error": message},
                str(task["task_id"]),
            )
        if orphaned:
            logger.warning("Recovered %d orphaned Vibe tasks after API restart", len(orphaned))

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
        sessions = await cursor.to_list(length=min(limit, 100))
        # Keep the session rail useful without duplicating prompt text into
        # the session document. The first user message is the stable preview
        # shown below the user-defined session title.
        messages = get_mongo_db()[self.message_collection]
        for session in sessions:
            first_message = await messages.find_one(
                {
                    "user_id": user_id,
                    "session_id": session["session_id"],
                    "role": "user",
                },
                {"_id": 0, "content": 1},
                sort=[("created_at", ASCENDING)],
            )
            session["first_prompt"] = str((first_message or {}).get("content") or "")
        return sessions

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
        await self._hydrate_runtime_messages(user_id, session_id)
        cursor = get_mongo_db()[self.message_collection].find(
            {"user_id": user_id, "session_id": session_id},
            {"_id": 0},
        ).sort("created_at", ASCENDING)
        return await cursor.to_list(length=500)

    async def _hydrate_runtime_messages(self, user_id: str, session_id: str) -> None:
        """Import assistant replies written by the embedded SessionStore.

        Older runs completed inside the vendored runtime before the adapter
        hydrated the final attempt result. Their replies are durable in the
        scoped JSONL store but absent from Mongo, so repair that boundary on
        session load without duplicating messages.
        """
        path = session_runtime_root(user_id, session_id) / "messages.jsonl"
        if not path.exists():
            return

        db = get_mongo_db()
        existing = await db[self.message_collection].find(
            {"user_id": user_id, "session_id": session_id, "role": "assistant"},
            {"_id": 0, "content": 1, "task_id": 1, "metadata.runtime_attempt_id": 1},
        ).to_list(length=500)
        existing_attempts = {
            str(item.get("metadata", {}).get("runtime_attempt_id"))
            for item in existing
            if item.get("metadata", {}).get("runtime_attempt_id")
        }
        existing_pairs = {
            (str(item.get("task_id") or ""), str(item.get("content") or ""))
            for item in existing
        }

        event_cursor = db[self.event_collection].find(
            {
                "user_id": user_id,
                "session_id": session_id,
                "task_id": {"$exists": True, "$ne": None},
            },
            {"_id": 0, "task_id": 1, "payload.attempt_id": 1},
        )
        attempt_to_task: Dict[str, str] = {}
        async for event in event_cursor:
            attempt_id = str(event.get("payload", {}).get("attempt_id") or "")
            task_id = str(event.get("task_id") or "")
            if attempt_id and task_id:
                attempt_to_task[attempt_id] = task_id

        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("role") != "assistant" or not str(message.get("content") or "").strip():
                continue
            attempt_id = str(message.get("linked_attempt_id") or "")
            task_id = attempt_to_task.get(attempt_id, "")
            content = str(message.get("content") or "")
            if attempt_id in existing_attempts or (task_id, content) in existing_pairs:
                continue
            if not task_id:
                logger.warning(
                    "Skipping runtime assistant message without task mapping: %s",
                    attempt_id,
                )
                continue
            metadata = dict(message.get("metadata") or {})
            metadata["runtime_attempt_id"] = attempt_id
            hydrated = VibeMessage(
                message_id=str(message.get("message_id") or new_id("msg")),
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=content,
                task_id=task_id,
                created_at=message.get("created_at") or utc_now(),
                metadata=metadata,
            )
            await db[self.message_collection].insert_one(hydrated.model_dump())
            existing_attempts.add(attempt_id)
            existing_pairs.add((task_id, content))

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

        async with self._message_submit_lock:
            existing = await get_mongo_db()[self.task_collection].find_one(
                {"user_id": user["id"], "session_id": session_id, "idempotency_key": idempotency_key},
                {"_id": 0},
            )
            if existing:
                return existing
            active = await get_mongo_db()[self.task_collection].find_one(
                {
                    "user_id": user["id"],
                    "status": {
                        "$in": [
                            VibeTaskStatus.queued.value,
                            VibeTaskStatus.processing.value,
                        ]
                    },
                },
                {"_id": 0},
                sort=[("updated_at", DESCENDING)],
            )
            if active:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "已有研究任务正在执行，请等待完成或先取消当前任务",
                        "task_id": active.get("task_id"),
                        "session_id": active.get("session_id"),
                    },
                )

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
            # 构建最终 prompt（可能包含个人投资助手上下文）
            # 注意：即使调用方传入了 profile_id，也必须以画像自身的
            # context_injection_enabled 开关为准，避免前端状态过期/传参错误
            # 导致用户已关闭的画像内容被强行注入（对应 spec: User disables
            # context injection）。
            final_prompt = payload.content
            # 画像上下文默认按当前登录用户解析，不能依赖前端传入 profile_id。
            # 旧版/缓存中的前端可能没有该字段，但用户仍然期望已保存持仓可用于研究。
            if HAS_CONTEXT_BUILDER:
                try:
                    from app.services.personal_investment.profile_service import profile_service
                    profile = await profile_service.get_profile(user["id"])
                    include_profile = bool(
                        profile and profile.get("context_injection_enabled", True)
                    )
                    if profile and not include_profile:
                        logger.info(
                            f"Profile context injection disabled by user for task {task_id}, skipping"
                        )

                    context_summary = None
                    if include_profile or payload.strategy_id:
                        context_summary = await ContextBuilder.build_context_summary(
                            user_id=user["id"],
                            include_profile=include_profile,
                            strategy_id=payload.strategy_id,
                        )
                    if context_summary:
                        # 将上下文前置到用户输入前
                        final_prompt = f"{context_summary}\n\n---\n\n{payload.content}"
                        logger.info(f"Injected investment context for task {task_id}")
                except Exception as e:
                    logger.warning(f"Failed to build investment context: {e}, using original prompt")

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
                    "prompt": final_prompt,
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
        # Runtime paths are persisted in the command, so validate them again
        # at the async boundary instead of trusting a queued payload.
        assert_within_user_scope(Path(command.runtime_root), command.user_id)
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
        db = get_mongo_db()
        await db[self.task_collection].update_one(
            {"user_id": user_id, "task_id": task_id},
            {"$set": patch},
        )
        task = await db[self.task_collection].find_one(
            {"user_id": user_id, "task_id": task_id},
            {"_id": 0, "session_id": 1},
        )
        if task:
            session_status = (
                "idle"
                if status in {
                    VibeTaskStatus.completed,
                    VibeTaskStatus.failed,
                    VibeTaskStatus.cancelled,
                }
                else status.value
            )
            await db[self.session_collection].update_one(
                {"user_id": user_id, "session_id": task["session_id"]},
                {"$set": {"status": session_status, "updated_at": utc_now()}},
            )

    async def get_task(self, user_id: str, task_id: str) -> Dict[str, Any]:
        task = await get_mongo_db()[self.task_collection].find_one({"user_id": user_id, "task_id": task_id}, {"_id": 0})
        if not task:
            raise HTTPException(status_code=404, detail="研究任务不存在")
        return self.task_center_row(task)

    async def submit_feedback(
        self,
        user: Dict[str, Any],
        session_id: str,
        task_id: str,
        feedback_type: str,
        content: str = "",
    ) -> Dict[str, Any]:
        """保存用户反馈并创建待复核的线上 Bad Case 候选。"""
        session = await self.get_session(user["id"], session_id)
        task = await get_mongo_db()[self.task_collection].find_one(
            {"user_id": user["id"], "session_id": session_id, "task_id": task_id},
            {"_id": 0},
        )
        if not task:
            raise HTTPException(status_code=404, detail="研究任务不存在")

        assistant = await get_mongo_db()[self.message_collection].find_one(
            {
                "user_id": user["id"],
                "session_id": session_id,
                "task_id": task_id,
                "role": "assistant",
            },
            {"_id": 0},
            sort=[("created_at", DESCENDING)],
        )
        if not assistant and not str(content or "").strip():
            raise HTTPException(status_code=400, detail="反馈缺少可关联的 Agent 输出")

        from app.models.eval import BadCaseSourceContext, DetectionSignal, FailureFamily, DetectionStatus, ReviewStatus
        from app.services.eval.bad_case_service import bad_case_service
        from app.services.eval.badcase_fingerprint import hash_user_id

        feedback_doc = {
            "feedback_id": new_id("feedback"),
            "user_id": user["id"],
            "session_id": session_id,
            "task_id": task_id,
            "feedback_type": feedback_type,
            "content": str(content or "")[:2000],
            "created_at": utc_now(),
        }
        await get_mongo_db()[self.feedback_collection].insert_one(feedback_doc)

        bad_case = await bad_case_service.create_online_bad_case(
            source="user_feedback",
            input_data={"prompt": task.get("prompt", "")},
            output_data={"content": assistant.get("content", "")} if assistant else None,
            failure_reason=content or feedback_type,
            risk_level="medium",
            failure_family=FailureFamily.USER_FEEDBACK.value,
            detection_signals=[
                DetectionSignal(
                    signal_type="user.feedback",
                    failure_family=FailureFamily.USER_FEEDBACK,
                    score=0.0,
                    confidence=0.7,
                    severity="medium",
                    reason=content or feedback_type,
                    evidence_refs=[task_id, session_id],
                    detector_name="user_feedback",
                    detector_version="1.0.0",
                )
            ],
            detection_confidence=0.7,
            detection_status=DetectionStatus.CANDIDATE.value,
            review_status=ReviewStatus.PENDING.value,
            review_required=True,
            source_context=BadCaseSourceContext(
                user_id_hash=hash_user_id(user["id"]),
                session_id=session_id,
                task_id=task_id,
                trace_id=f"online_{task_id}",
                replayable=True,
            ),
            created_by=user.get("username", "user"),
            tags=["user_feedback", f"feedback:{feedback_type}"],
        )
        return {"feedback": {key: value for key, value in feedback_doc.items() if key != "_id"}, "bad_case": bad_case, "session_id": session["session_id"]}

    async def list_tasks(
        self,
        user_id: str,
        status: Optional[str],
        page: int,
        page_size: int,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {"user_id": user_id}
        if status:
            query["status"] = status
        if session_id:
            query["session_id"] = session_id
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

        # Online Bad Case detection is deliberately asynchronous: scoring and
        # persistence must never delay the production event stream.
        if task_id and raw_type in {"attempt.failed", "attempt.completed", "attempt.cancelled"}:
            try:
                from app.services.eval.online_badcase_service import online_badcase_collector

                collection_task = asyncio.create_task(
                    online_badcase_collector.collect_from_online_event(
                        user_id=user_id,
                        session_id=session_id,
                        task_id=str(task_id),
                        raw_type=raw_type,
                        payload=payload,
                    )
                )
                self._background_tasks.add(collection_task)
                collection_task.add_done_callback(self._background_tasks.discard)
            except Exception:
                logger.warning("failed to schedule online Bad Case collection", exc_info=True)


vibe_agent_service = VibeAgentService()
