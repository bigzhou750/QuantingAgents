"""Owner-scope checks for in-memory, Redis queue, and Mongo analysis tasks."""

import pytest

from app.services.memory_state_manager import MemoryStateManager, TaskStatus
from app.services.queue_service import QueueService
from app.services import simple_analysis_service


@pytest.mark.asyncio
async def test_memory_task_stats_and_deletion_are_user_scoped():
    manager = MemoryStateManager()
    await manager.create_task("task-a", "user-a", "000001")
    await manager.create_task("task-b", "user-b", "000002")

    a_stats = await manager.get_statistics(user_id="user-a")
    b_stats = await manager.get_statistics(user_id="user-b")
    assert a_stats["total_tasks"] == 1
    assert b_stats["total_tasks"] == 1
    assert await manager.remove_task("task-b", user_id="user-a") is False
    assert await manager.get_user_task_dict("user-b", "task-b") is not None


class _FakeRedisTask:
    def __init__(self):
        self.tasks = {
            "qa:task:1": {"id": "1", "user": "user-a", "status": "queued"},
            "qa:task:2": {"id": "2", "user": "user-b", "status": "queued"},
        }

    async def hgetall(self, key):
        return dict(self.tasks.get(key, {}))

    async def hset(self, key, mapping):
        self.tasks.setdefault(key, {}).update(mapping)

    async def lrem(self, *args):
        return 0

    async def scard(self, key):
        return 0

    async def srem(self, key, *values):
        return 0

    async def lpush(self, *args):
        return 0

    async def hdel(self, *args):
        return 0

    async def sadd(self, *args):
        return 1

    async def srem(self, *args):
        return 1

    async def expire(self, *args):
        return True

    async def delete(self, *args):
        return 1


@pytest.mark.asyncio
async def test_queue_cancel_requires_matching_owner():
    service = QueueService(_FakeRedisTask())
    assert await service.get_user_task("1", "user-a") is not None
    assert await service.get_user_task("1", "user-b") is None
    assert await service.cancel_task("1", user_id="user-a") is True
    assert await service.cancel_task("2", user_id="user-a") is False
    assert await service.ack_task("2", True, user_id="user-b") is True
    assert await service.ack_task("1", True, user_id="user-b") is False


class _FakeMemoryTasks:
    def __init__(self):
        self.calls = []

    async def list_all_tasks(self, status=None, limit=20, offset=0, user_id=None):
        self.calls.append(user_id)
        return [{"task_id": "mem-a", "user_id": "user-a"}]


class _FilteringCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    def limit(self, n):
        return self

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _FakeTaskCollection:
    def __init__(self, docs):
        self.docs = docs

    async def count_documents(self, query):
        return len(self._matches(query))

    def find(self, query):
        return _FilteringCursor(self._matches(query))

    def _matches(self, query):
        owner = query.get("$or", [{}])[0].get("user_id")
        return [doc for doc in self.docs if doc.get("user_id") == owner or doc.get("user") == owner]


@pytest.mark.asyncio
async def test_analysis_mongo_list_always_filters_owner(monkeypatch):
    docs = [
        {"task_id": "mongo-a", "user_id": "user-a"},
        {"task_id": "mongo-b", "user_id": "user-b"},
    ]
    fake_db = {"analysis_tasks": _FakeTaskCollection(docs)}

    def fake_get_mongo_db():
        return fake_db

    monkeypatch.setattr(simple_analysis_service, "get_mongo_db", fake_get_mongo_db)
    service = object.__new__(simple_analysis_service.SimpleAnalysisService)
    service._stock_name_cache = {}
    service.memory_manager = _FakeMemoryTasks()

    a_tasks = await service.list_all_tasks(user_id="user-a")
    b_tasks = await service.list_all_tasks(user_id="user-b")

    ids_a = {task["task_id"] for task in a_tasks}
    ids_b = {task["task_id"] for task in b_tasks}
    assert "mongo-a" in ids_a
    assert "mongo-b" not in ids_a
    assert "mongo-b" in ids_b
    with pytest.raises(RuntimeError, match="scope"):
        await service.list_all_tasks()
