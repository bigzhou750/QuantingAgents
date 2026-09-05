from app.core.ownership import owner_filter, ensure_owner_indexes
from app.core.ownership import assert_owner
from app.scripts.migrate_user_ownership import classify_documents
from app.scripts.migrate_user_ownership import apply_migration, require_migration_version
from app.scripts.rollback_user_ownership import rollback_versions
import pytest
from fastapi import HTTPException


def test_owner_filter_cannot_be_overridden_by_payload():
    query = owner_filter("user-a", task_id="t1")
    assert query == {"task_id": "t1", "user_id": "user-a"}


def test_assert_owner_rejects_document_without_owner():
    with pytest.raises(HTTPException):
        assert_owner({}, "user-a")


def test_migration_is_dry_run_and_isolates_unknown_records():
    report, updates, isolated = classify_documents(
        "analysis_tasks",
        [{"_id": 1, "username": "alice"}, {"_id": 2}],
        {"alice": "user-a"},
    )
    assert report.scanned == 2
    assert report.mapped == 1
    assert report.missing == 1
    assert updates == [{"_id": 1, "user_id": "user-a"}]
    assert [item["_id"] for item in isolated] == [2]


class _FakeMigrationDb:
    def __init__(self):
        self.versions = []
        self.updated = []

    def __getitem__(self, name):
        return _FakeMigrationCollection(name, self)


class _FakeMigrationCollection:
    def __init__(self, name, db):
        self.name = name
        self.db = db
        self.docs = []

    async def update_one(self, query, update, upsert=False):
        self.db.updated.append((self.name, query, update))
        return None

    async def insert_many(self, docs, ordered=False):
        self.docs.extend(docs)
        return None

    async def find_one(self, query):
        if self.name == "migration_versions":
            return next((v for v in self.db.versions if v == query), None)
        return None


def _fake_update_one(*args, **kwargs):
    return None


def test_apply_migration_records_version_and_require_version_fails_closed(monkeypatch):
    db = _FakeMigrationDb()

    async def run():
        report = await apply_migration(db, "analysis_tasks", [{"_id": 1, "user_id": "u1"}], [], version=2)
        assert report.mapped == 1
        try:
            await require_migration_version(db, "analysis_tasks", 3)
            raise AssertionError("missing migration version must fail closed")
        except RuntimeError:
            pass
    import asyncio
    asyncio.run(run())


def test_rollback_removes_only_version_bookkeeping():
    class _FakeVersions:
        def delete_many(self, query):
            return type("Result", (), {"deleted_count": 1})()
    db = {"migration_versions": _FakeVersions()}
    result = rollback_versions(db, 2)
    assert result["rolled_back_entries"] == 1
    assert result["owner_fields_preserved"] is True
    assert result["isolation_preserved"] is True


def test_owner_indexes_are_created_for_private_collections():
    class _FakeIndexCollection:
        def __init__(self):
            self.indexes = []

        async def create_index(self, fields, unique=False):
            self.indexes.append((fields, unique))

    class _FakeIndexDb:
        def __init__(self):
            self.collections = {name: _FakeIndexCollection() for name in ("analysis_tasks", "favorites", "investment_profiles")}

        def __getitem__(self, name):
            if name not in self.collections:
                self.collections[name] = _FakeIndexCollection()
            return self.collections[name]

    db = _FakeIndexDb()

    async def run():
        await ensure_owner_indexes(db)

    import asyncio
    asyncio.run(run())
    assert db.collections["analysis_tasks"].indexes
    assert db.collections["favorites"].indexes[0] == ([("user_id", 1), ("stock_code", 1)], True)
    assert db.collections["investment_profiles"].indexes[0] == ([("user_id", 1)], True)


def test_ab_resource_crud_is_isolated_by_owner_filter():
    class _Cursor:
        def __init__(self, docs):
            self.docs = docs

        def to_list(self, length):
            return self.docs[:length]

    class _Collection:
        def __init__(self):
            self.docs = []

        async def insert_one(self, doc):
            self.docs.append(doc)

        def find(self, query):
            return _Cursor([doc for doc in self.docs if all(doc.get(k) == v for k, v in query.items())])

        async def find_one(self, query):
            return next((doc for doc in self.docs if all(doc.get(k) == v for k, v in query.items())), None)

        async def delete_one(self, query):
            before = len(self.docs)
            self.docs = [doc for doc in self.docs if not all(doc.get(k) == v for k, v in query.items())]
            return type("Result", (), {"deleted_count": before - len(self.docs)})()

    collection = _Collection()
    await_collection = collection

    async def create(user_id, payload):
        doc = {**payload, "user_id": user_id}
        await await_collection.insert_one(doc)
        return doc

    async def read(user_id, resource_id):
        return await await_collection.find_one(owner_filter(user_id, resource_id=resource_id))

    async def delete(user_id, resource_id):
        return (await await_collection.delete_one(owner_filter(user_id, resource_id=resource_id))).deleted_count

    import asyncio

    async def run():
        await create("user-a", {"resource_id": "r1", "name": "A private"})
        await create("user-b", {"resource_id": "r1", "name": "B private"})
        assert (await read("user-a", "r1"))["name"] == "A private"
        assert (await read("user-b", "r1"))["name"] == "B private"
        assert (await read("user-a", "missing")) is None
        assert (await delete("user-b", "r1")) == 1
        assert (await read("user-a", "r1"))["name"] == "A private"

    asyncio.run(run())
