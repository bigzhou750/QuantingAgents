import asyncio
import json
import multiprocessing
import os

from app.services.queue_service import QueueService


class _FileRedis:
    def __init__(self, path):
        self.path = str(path)
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump({}, fh)

    def _read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, data):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)

    async def hset(self, key, mapping):
        data = self._read()
        data.setdefault(key, {}).update({str(k): str(v) for k, v in mapping.items()})
        self._write(data)

    async def hgetall(self, key):
        return dict(self._read().get(key, {}))

    async def hdel(self, key, *fields):
        data = self._read()
        if key in data:
            for field in fields:
                data[key].pop(field, None)
        self._write(data)
        return len(fields)

    async def lpush(self, key, *values):
        data = self._read()
        data[key] = list(values) + data.get(key, [])
        self._write(data)
        return len(values)

    async def rpop(self, key):
        data = self._read()
        values = data.get(key, [])
        if not values:
            return None
        value = values.pop()
        self._write(data)
        return value

    async def llen(self, key):
        return len(self._read().get(key, []))

    async def sadd(self, key, *values):
        data = self._read()
        members = set(data.get(key, []))
        before = len(members)
        members.update(str(v) for v in values)
        data[key] = sorted(members)
        self._write(data)
        return len(members) - before

    async def scard(self, key):
        return len(self._read().get(key, []))

    async def srem(self, key, *values):
        data = self._read()
        members = set(data.get(key, []))
        before = len(members)
        members.difference_update(str(v) for v in values)
        data[key] = sorted(members)
        self._write(data)
        return before - len(members)

    async def expire(self, key, ttl):
        return True

    async def delete(self, key):
        data = self._read()
        existed = key in data
        data.pop(key, None)
        self._write(data)
        return int(existed)


def _child_worker(redis_path, out_q):
    async def main():
        service = QueueService(_FileRedis(redis_path))
        task = await service.dequeue_task("child-worker")
        if not task:
            out_q.put({"error": "no task"})
            return
        owner = str(task.get("owner_id", ""))
        user = str(task.get("user", ""))
        await service.ack_task(task["id"], True, user_id=owner)
        out_q.put({"owner_id": owner, "user": user})

    asyncio.run(main())


def test_queue_owner_survives_cross_process_dequeue(tmp_path):
    redis_path = tmp_path / "queue.json"
    redis = _FileRedis(redis_path)
    service = QueueService(redis)

    asyncio.run(service.enqueue_task("user-a", "000001", {"depth": "quick"}))

    out_q = multiprocessing.get_context("spawn").Queue()
    proc = multiprocessing.get_context("spawn").Process(
        target=_child_worker,
        args=(str(redis_path), out_q),
    )
    proc.start()
    proc.join(timeout=30)
    assert proc.exitcode == 0
    result = out_q.get(timeout=10)
    assert result == {"owner_id": "user-a", "user": "user-a"}
