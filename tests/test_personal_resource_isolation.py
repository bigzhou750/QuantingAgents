"""A/B isolation checks for user-owned personal resource services."""

import pytest
from bson import ObjectId

from app.services.favorites_service import FavoritesService
from app.services.personal_investment.observation_service import ObservationService
from app.services.personal_investment.strategy_service import StrategyService
from app.services.tags_service import TagsService
from app.models.observation import ObservationRecord
from app.models.notification import NotificationCreate
from app.services import notifications_service as notifications_service_mod


class _Result:
    def __init__(self, matched=0, modified=0, deleted=0, upserted=None):
        self.matched_count = matched
        self.modified_count = modified
        self.deleted_count = deleted
        self.upserted_id = upserted


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length):
        return list(self._docs)[:length]


class _FakeColl:
    def __init__(self):
        self.docs = []

    async def create_index(self, *args, **kwargs):
        return None

    async def insert_one(self, doc):
        doc["_id"] = ObjectId()
        self.docs.append(doc)
        return type("Insert", (), {"inserted_id": doc["_id"]})()

    async def find_one(self, query):
        return self._first(query)

    def find(self, query):
        return _Cursor([doc for doc in self.docs if self._match(doc, query)])

    async def count_documents(self, query):
        return len([doc for doc in self.docs if self._match(doc, query)])

    async def update_one(self, query, update, upsert=False):
        doc = self._first(query)
        if doc is None and upsert:
            doc = dict(query)
            doc.update(update.get("$setOnInsert", {}))
            doc["_id"] = ObjectId()
            self.docs.append(doc)
            matched, modified = 0, 1
        elif doc is None:
            return _Result(matched=0, modified=0)
        else:
            matched = modified = 1
        for key, value in update.get("$set", {}).items():
            doc[key] = value
        for key, value in update.get("$setOnInsert", {}).items():
            doc.setdefault(key, value)
        if "$push" in update:
            for key, value in update["$push"].items():
                doc.setdefault(key, []).append(value)
        if "$pull" in update:
            for key, value in update["$pull"].items():
                doc[key] = [item for item in doc.get(key, []) if not self._match(item, value)]
        return _Result(matched=matched, modified=modified, upserted=doc.get("_id") if upsert and doc else None)

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._match(doc, query)]
        return _Result(deleted=before - len(self.docs))

    async def delete_many(self, query):
        return await self.delete_one(query)

    def _first(self, query):
        return next((doc for doc in self.docs if self._match(doc, query)), None)

    @staticmethod
    def _match(doc, query):
        return all(doc.get(key) == value for key, value in query.items())


class _FakeDb:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _FakeColl())

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]


@pytest.mark.asyncio
async def test_favorites_are_user_scoped():
    db = _FakeDb()
    service = FavoritesService()
    service.db = db

    await service.add_favorite("user-a", "000001", "A stock")
    await service.add_favorite("user-b", "000001", "B stock")

    a_codes = {item["stock_code"] for item in await service.get_user_favorites("user-a")}
    b_codes = {item["stock_code"] for item in await service.get_user_favorites("user-b")}
    assert a_codes == {"000001"}
    assert b_codes == {"000001"}
    assert db["user_favorites"].docs[0]["user_id"] == "user-a"


@pytest.mark.asyncio
async def test_strategy_and_observation_detail_are_user_scoped(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.services.personal_investment.strategy_service.get_mongo_db", lambda: db)
    monkeypatch.setattr("app.services.personal_investment.observation_service.get_mongo_db", lambda: db)

    strategy = StrategyService()
    a = await strategy.create_strategy("user-a", "A strategy")
    b = await strategy.create_strategy("user-b", "B strategy")
    assert (await strategy.get_strategy(a["strategy_id"]))["user_id"] == "user-a"
    assert await strategy.get_strategy(b["strategy_id"], user_id="user-a") is None

    observations = ObservationService()
    await observations.add_observation("user-a", ObservationRecord(user_id="user-a", stock_code="000001"))
    await observations.add_observation("user-b", ObservationRecord(user_id="user-b", stock_code="000001"))
    a_items = (await observations.list_observations("user-a", limit=100))["items"]
    assert len(a_items) == 1


@pytest.mark.asyncio
async def test_user_tags_are_user_scoped(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.services.tags_service.get_mongo_db", lambda: db)
    tags = TagsService()
    await tags.create_tag("user-a", "alpha")
    await tags.create_tag("user-b", "alpha")
    assert [tag["name"] for tag in await tags.list_tags("user-a")] == ["alpha"]
    assert [tag["name"] for tag in await tags.list_tags("user-b")] == ["alpha"]


@pytest.mark.asyncio
async def test_notifications_are_user_scoped(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(notifications_service_mod, "get_mongo_db", lambda: db)

    async def noop_send(*args, **kwargs):
        return None
    monkeypatch.setattr("app.routers.websocket_notifications.send_notification_via_websocket", noop_send)

    service = notifications_service_mod.NotificationsService()
    await service.create_and_publish(NotificationCreate(
        user_id="user-a",
        type="analysis",
        title="A alert",
        content="A private",
        link="/a",
    ))
    await service.create_and_publish(NotificationCreate(
        user_id="user-b",
        type="analysis",
        title="B alert",
        content="B private",
        link="/b",
    ))

    a_items = (await service.list("user-a")).items
    b_items = (await service.list("user-b")).items
    assert [item.title for item in a_items] == ["A alert"]
    assert [item.title for item in b_items] == ["B alert"]
    assert await service.mark_read("user-a", str(b_items[0].id)) is False
