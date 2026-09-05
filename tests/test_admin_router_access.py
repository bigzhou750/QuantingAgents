from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import config, database, logs, cache, multi_source_sync, scheduler
from app.routers.auth_db import get_current_user


def test_sensitive_operational_routers_are_admin_only():
    app = FastAPI()
    app.include_router(config.router)
    app.include_router(database.router)
    app.include_router(logs.router)
    app.include_router(cache.router)
    app.include_router(multi_source_sync.router)
    app.include_router(scheduler.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-a",
        "username": "alice",
        "is_admin": False,
    }
    app.dependency_overrides[scheduler.get_scheduler_service] = lambda: object()
    client = TestClient(app)

    assert client.get("/config/llm/providers").status_code == 403
    assert client.get("/database/status").status_code == 403
    assert client.get("/system-logs/files").status_code == 403
    assert client.get("/api/cache/stats").status_code == 403
    assert client.get("/api/sync/multi-source/sources/status").status_code == 403
    assert client.get("/api/scheduler/jobs").status_code == 403
