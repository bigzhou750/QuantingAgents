"""Live MongoDB/Redis isolation checks.

Run explicitly with an isolated database and Redis DB:
MONGODB_DATABASE_SCOPE=explicit MONGODB_DATABASE=quantingagents_iso_test \
REDIS_DB=15 RUN_LIVE_ISOLATION_TESTS=1 pytest -q tests/test_live_isolation_integration.py
"""

import os
from pathlib import Path
import uuid

import pytest

from app.core.database import close_db, get_mongo_db, get_redis_client, init_db
from app.services.auth_service import AuthService
from app.services.queue_service import QueueService
from app.services.user_service import user_service
from app.services.vibe_agent.scoped_memory import ScopedPersistentMemory


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_ISOLATION_TESTS") != "1",
    reason="live MongoDB/Redis test is opt-in",
)


@pytest.mark.asyncio
async def test_live_mongo_redis_token_queue_and_runtime_isolation(tmp_path: Path):
    await init_db()
    db = get_mongo_db()
    redis = get_redis_client()
    suffix = uuid.uuid4().hex[:10]
    user_a = f"live-a-{suffix}"
    user_b = f"live-b-{suffix}"
    task_a = f"live-task-a-{suffix}"
    task_b = f"live-task-b-{suffix}"
    jti = f"live-jti-{suffix}"
    rotated = f"live-jti-rotated-{suffix}"

    try:
        await db.analysis_tasks.insert_many([
            {"task_id": task_a, "user_id": user_a, "status": "completed"},
            {"task_id": task_b, "user_id": user_b, "status": "completed"},
        ])
        assert await db.analysis_tasks.count_documents({"task_id": task_a, "user_id": user_b}) == 0
        assert await db.analysis_tasks.count_documents({"task_id": task_b, "user_id": user_b}) == 1

        queue = QueueService(redis)
        queued_id = await queue.enqueue_task(user_a, "000001", {"source": "live"})
        queued = await queue.get_user_task(queued_id, user_a)
        assert queued and queued["owner_id"] == user_a
        assert await queue.get_user_task(queued_id, user_b) is None
        assert await queue.cancel_task(queued_id, user_b) is False
        await redis.lrem("qa:ready", 0, queued_id)
        await redis.delete(f"qa:task:{queued_id}")

        access = AuthService.create_access_token(sub=user_a, user_id=user_a)
        assert AuthService.verify_token(access).user_id == user_a
        assert await user_service.create_refresh_session(
            user_id=user_a,
            jti=jti,
            expires_at=__import__("datetime").datetime.utcnow() + __import__("datetime").timedelta(days=1),
        )
        assert await user_service.rotate_refresh_session(
            user_id=user_a,
            old_jti=jti,
            new_jti=rotated,
            expires_at=__import__("datetime").datetime.utcnow() + __import__("datetime").timedelta(days=1),
        )
        assert not await user_service.rotate_refresh_session(
            user_id=user_a,
            old_jti=jti,
            new_jti=f"replay-{suffix}",
            expires_at=__import__("datetime").datetime.utcnow() + __import__("datetime").timedelta(days=1),
        )

        memory_a = ScopedPersistentMemory(user_id=user_a, memory_dir=tmp_path / "a")
        memory_b = ScopedPersistentMemory(user_id=user_b, memory_dir=tmp_path / "b")
        memory_a.save("live preference", "private A")
        memory_b.save("live preference", "private B")
        assert not any("private A" in item.body for item in memory_b.recall("live preference"))
    finally:
        await db.analysis_tasks.delete_many({"task_id": {"$in": [task_a, task_b]}})
        await db.refresh_sessions.delete_many({"jti": {"$in": [jti, rotated]}})
        await close_db()
