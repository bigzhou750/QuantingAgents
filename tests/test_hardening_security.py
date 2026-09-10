from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.analysis import SingleAnalysisRequest
from app.routers import config as config_router
from app.routers.auth_db import get_current_user, router as auth_router


def _config_app(role: str) -> FastAPI:
    app = FastAPI()
    app.include_router(config_router.router, prefix="/api")
    user = {
        "id": "u1",
        "username": "alice",
        "is_admin": role == "admin",
    }
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_regular_user_cannot_write_llm_provider():
    app = _config_app("user")
    with TestClient(app) as client:
        resp = client.post("/api/config/llm/providers", json={"name": "openai"})
        assert resp.status_code == 403


def test_regular_user_cannot_write_llm_config():
    app = _config_app("user")
    with TestClient(app) as client:
        resp = client.post("/api/config/llm", json={})
        assert resp.status_code == 403


def test_analysis_request_rejects_client_model_credentials():
    try:
        SingleAnalysisRequest(parameters={"api_key": "sk-client-secret-value"})
    except ValidationError:
        return
    raise AssertionError("analysis request should reject client model credentials")


def test_registration_status_is_public():
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    with TestClient(app) as client:
        resp = client.get("/api/auth/registration-status")
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] is True
