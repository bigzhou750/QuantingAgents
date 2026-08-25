from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.routers.auth_db import get_current_user
from app.services.vibe_agent.models import VibeMessageCreate, VibeSessionCreate, VibeSessionUpdate
from app.services.vibe_agent.service import api_response, vibe_agent_service

router = APIRouter()


@router.get("/health")
async def health(_: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.health())


@router.get("/capabilities")
async def capabilities(_: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.capabilities())


@router.post("/sessions")
async def create_session(payload: VibeSessionCreate, user: dict = Depends(get_current_user)):
    return api_response((await vibe_agent_service.create_session(user, payload)).model_dump(), "会话已创建")


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    archived: bool = False,
    user: dict = Depends(get_current_user),
):
    return api_response(await vibe_agent_service.list_sessions(user["id"], limit, archived))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.get_session(user["id"], session_id))


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, payload: VibeSessionUpdate, user: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.update_session(user["id"], session_id, payload), "会话已更新")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    await vibe_agent_service.delete_session(user["id"], session_id)
    return api_response({"session_id": session_id}, "会话已归档")


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str, user: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.list_messages(user["id"], session_id))


@router.post("/sessions/{session_id}/messages")
async def create_message(session_id: str, payload: VibeMessageCreate, user: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.create_message_task(user, session_id, payload), "研究任务已入队")


@router.get("/sessions/{session_id}/events")
async def stream_events(
    session_id: str,
    after: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    return StreamingResponse(
        vibe_agent_service.event_stream(user["id"], session_id, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/events/replay")
async def replay_events(session_id: str, after: int = Query(default=0, ge=0), user: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.replay_events(user["id"], session_id, after))


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    return api_response(await vibe_agent_service.list_tasks(user["id"], status, page, page_size))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.get_task(user["id"], task_id))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, user: dict = Depends(get_current_user)):
    return api_response(await vibe_agent_service.cancel_task(user, task_id), "任务已取消")
