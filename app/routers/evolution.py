"""
Agent 自进化闭环 API 路由

提供 artifact 注册、候选提案管理、验证运行、审批、promote/rollback、
回执查询和审计日志等功能。仅允许管理员访问。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.routers.auth_db import get_current_user
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 请求/响应模型 ====================

class ApiResponse(BaseModel):
    success: bool = True
    data: dict = {}
    message: str = ""


class ArtifactRegisterRequest(BaseModel):
    artifact_type: str  # skill/prompt/policy/rubric/case
    name: str
    path: str = ""
    owner: str = "system"
    content_snapshot: Optional[dict] = None
    rollback_strategy: str = "previous_stable"


class RollbackRequest(BaseModel):
    target_version: str
    reason: str = ""


class ApprovalRequest(BaseModel):
    comment: str = ""


class StopRequest(BaseModel):
    reason: str = "manual"


class EvolutionConfigUpdate(BaseModel):
    automation_mode: Optional[str] = None
    trigger_regression_threshold: Optional[float] = None
    trigger_bad_case_count: Optional[int] = None
    budget_max_runs_per_day: Optional[int] = None
    human_gate: Optional[bool] = None
    schedule_cron: Optional[str] = None


# ==================== 权限检查 ====================

async def verify_evolution_access(current_user: dict = Depends(get_current_user)) -> dict:
    """验证自进化平台访问权限"""
    if not settings.EVAL_PLATFORM_ENABLED:
        raise HTTPException(status_code=403, detail="评测平台未启用")
    if not settings.EVOLUTION_ENABLED:
        raise HTTPException(status_code=403, detail="自进化功能未启用，请联系管理员开启 EVOLUTION_ENABLED")
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="仅管理员可访问自进化平台")
    return current_user


# ==================== Health & Config ====================

@router.get("/health", dependencies=[Depends(verify_evolution_access)])
async def health_check():
    """健康检查"""
    return ApiResponse(success=True, data={"status": "ok", "enabled": settings.EVOLUTION_ENABLED})


@router.get("/config", dependencies=[Depends(verify_evolution_access)])
async def get_config():
    """获取自进化配置"""
    return ApiResponse(success=True, data={
        "enabled": settings.EVOLUTION_ENABLED,
        "automation_mode": settings.EVOLUTION_AUTOMATION_MODE,
        "trigger_regression_threshold": settings.EVOLUTION_TRIGGER_REGRESSION_THRESHOLD,
        "trigger_bad_case_count": settings.EVOLUTION_TRIGGER_BAD_CASE_COUNT,
        "budget_max_runs_per_day": settings.EVOLUTION_BUDGET_MAX_RUNS_PER_DAY,
        "human_gate": settings.EVOLUTION_HUMAN_GATE,
        "allowed_artifact_types": settings.EVOLUTION_ALLOWED_ARTIFACT_TYPES,
        "schedule_cron": settings.EVOLUTION_SCHEDULE_CRON,
    })


@router.put("/config", dependencies=[Depends(verify_evolution_access)])
async def update_config(update: EvolutionConfigUpdate):
    """更新自进化配置（运行时覆盖，不持久化到 env）"""
    updated = {}
    if update.automation_mode is not None:
        settings.EVOLUTION_AUTOMATION_MODE = update.automation_mode
        updated["automation_mode"] = update.automation_mode
    if update.trigger_regression_threshold is not None:
        settings.EVOLUTION_TRIGGER_REGRESSION_THRESHOLD = update.trigger_regression_threshold
        updated["trigger_regression_threshold"] = update.trigger_regression_threshold
    if update.trigger_bad_case_count is not None:
        settings.EVOLUTION_TRIGGER_BAD_CASE_COUNT = update.trigger_bad_case_count
        updated["trigger_bad_case_count"] = update.trigger_bad_case_count
    if update.budget_max_runs_per_day is not None:
        settings.EVOLUTION_BUDGET_MAX_RUNS_PER_DAY = update.budget_max_runs_per_day
        updated["budget_max_runs_per_day"] = update.budget_max_runs_per_day
    if update.human_gate is not None:
        settings.EVOLUTION_HUMAN_GATE = update.human_gate
        updated["human_gate"] = update.human_gate
    if update.schedule_cron is not None:
        settings.EVOLUTION_SCHEDULE_CRON = update.schedule_cron
        updated["schedule_cron"] = update.schedule_cron
    return ApiResponse(success=True, data=updated, message="配置已更新")


# ==================== Artifact Registry ====================

@router.get("/artifacts", dependencies=[Depends(verify_evolution_access)])
async def list_artifacts(artifact_type: Optional[str] = None, skip: int = 0, limit: int = 50):
    """列出已注册的 artifact"""
    from app.services.evolution.artifact_registry import artifact_registry
    type_enum = None
    if artifact_type:
        from app.models.evolution import ArtifactType
        try:
            type_enum = ArtifactType(artifact_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid artifact type: {artifact_type}")
    artifacts = await artifact_registry.list_artifacts(type_enum, skip, limit)
    return ApiResponse(success=True, data={
        "items": [a.model_dump(by_alias=True, exclude={"id"}) for a in artifacts],
        "total": len(artifacts),
    })


@router.post("/artifacts", dependencies=[Depends(verify_evolution_access)])
async def register_artifact(request: ArtifactRegisterRequest):
    """注册新 artifact"""
    from app.services.evolution.artifact_registry import artifact_registry
    from app.models.evolution import ArtifactType
    try:
        art_type = ArtifactType(request.artifact_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid artifact type: {request.artifact_type}")
    try:
        entry = await artifact_registry.register(
            artifact_type=art_type,
            name=request.name,
            path=request.path,
            owner=request.owner,
            content_snapshot=request.content_snapshot,
            rollback_strategy=request.rollback_strategy,
        )
        return ApiResponse(success=True, data=entry.model_dump(by_alias=True, exclude={"id"}), message="Artifact registered")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/artifacts/{artifact_id}", dependencies=[Depends(verify_evolution_access)])
async def get_artifact(artifact_id: str):
    """获取 artifact 详情"""
    from app.services.evolution.artifact_registry import artifact_registry
    entry = await artifact_registry.get_registry_entry(artifact_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Artifact not found")
    current = await artifact_registry.get_current_version(artifact_id)
    data = entry.model_dump(by_alias=True, exclude={"id"})
    if current:
        data["current_version_detail"] = current.model_dump(by_alias=True, exclude={"id"})
    return ApiResponse(success=True, data=data)


@router.get("/artifacts/{artifact_id}/versions", dependencies=[Depends(verify_evolution_access)])
async def list_artifact_versions(artifact_id: str, skip: int = 0, limit: int = 50):
    """列出 artifact 的所有版本"""
    from app.services.evolution.artifact_registry import artifact_registry
    versions = await artifact_registry.list_versions(artifact_id, skip, limit)
    return ApiResponse(success=True, data={
        "items": [v.model_dump(by_alias=True, exclude={"id"}) for v in versions],
        "total": len(versions),
    })


@router.post("/artifacts/{artifact_id}/rollback", dependencies=[Depends(verify_evolution_access)])
async def rollback_artifact(artifact_id: str, request: RollbackRequest, user: dict = Depends(verify_evolution_access)):
    """回滚 artifact 到指定版本"""
    from app.services.evolution.artifact_registry import artifact_registry
    try:
        version = await artifact_registry.rollback(artifact_id, request.target_version, rolled_back_by=user.get("username", "admin"))
        return ApiResponse(success=True, data=version.model_dump(by_alias=True, exclude={"id"}), message=f"Rolled back to {request.target_version}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Proposals ====================

@router.get("/proposals", dependencies=[Depends(verify_evolution_access)])
async def list_proposals(status: Optional[str] = None, artifact_type: Optional[str] = None, skip: int = 0, limit: int = 50):
    """列出候选提案"""
    from app.services.evolution.proposal_service import proposal_service
    proposals = await proposal_service.list_proposals(status, artifact_type, skip, limit)
    stats = await proposal_service.get_stats()
    return ApiResponse(success=True, data={
        "items": [p.model_dump(by_alias=True, exclude={"id"}) for p in proposals],
        "total": stats["total"],
        "stats": stats["by_status"],
    })


@router.get("/proposals/{proposal_id}", dependencies=[Depends(verify_evolution_access)])
async def get_proposal(proposal_id: str):
    """获取提案详情"""
    from app.services.evolution.proposal_service import proposal_service
    proposal = await proposal_service.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return ApiResponse(success=True, data=proposal.model_dump(by_alias=True, exclude={"id"}))


@router.post("/proposals/{proposal_id}/verify", dependencies=[Depends(verify_evolution_access)])
async def verify_proposal(proposal_id: str):
    """触发候选验证"""
    from app.services.evolution.proposal_service import proposal_service
    from app.services.evolution.verification_service import verification_service
    proposal = await proposal_service.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.forbidden_target:
        raise HTTPException(status_code=403, detail="Cannot verify forbidden target proposal")
    try:
        verification = await verification_service.run_verification(proposal_id)
        return ApiResponse(success=True, data=verification.model_dump(by_alias=True, exclude={"id"}), message="Verification started")
    except Exception as e:
        logger.error(f"Verification failed for {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals/{proposal_id}/verification", dependencies=[Depends(verify_evolution_access)])
async def get_verification(proposal_id: str):
    """获取验证结果"""
    from app.services.evolution.verification_service import verification_service
    verifications = await verification_service.list_by_proposal(proposal_id)
    if not verifications:
        return ApiResponse(success=True, data={"items": [], "message": "No verification runs yet"})
    return ApiResponse(success=True, data={
        "items": [v.model_dump(by_alias=True, exclude={"id"}) for v in verifications],
    })


# ==================== Approval ====================

@router.post("/proposals/{proposal_id}/approve", dependencies=[Depends(verify_evolution_access)])
async def approve_proposal(proposal_id: str, request: ApprovalRequest, user: dict = Depends(verify_evolution_access)):
    """批准提案"""
    from app.services.evolution.approval_service import approval_service
    record = await approval_service.approve(proposal_id, user.get("username", "admin"), request.comment)
    return ApiResponse(success=True, data=record, message="Proposal approved")


@router.post("/proposals/{proposal_id}/reject", dependencies=[Depends(verify_evolution_access)])
async def reject_proposal(proposal_id: str, request: ApprovalRequest, user: dict = Depends(verify_evolution_access)):
    """拒绝提案"""
    from app.services.evolution.approval_service import approval_service
    record = await approval_service.reject(proposal_id, user.get("username", "admin"), request.comment)
    return ApiResponse(success=True, data=record, message="Proposal rejected")


@router.post("/proposals/{proposal_id}/comment", dependencies=[Depends(verify_evolution_access)])
async def comment_proposal(proposal_id: str, request: ApprovalRequest, user: dict = Depends(verify_evolution_access)):
    """添加评论"""
    from app.services.evolution.approval_service import approval_service
    record = await approval_service.comment(proposal_id, user.get("username", "admin"), request.comment)
    return ApiResponse(success=True, data=record, message="Comment added")


@router.get("/proposals/{proposal_id}/audit", dependencies=[Depends(verify_evolution_access)])
async def get_audit_trail(proposal_id: str):
    """获取审批审计记录"""
    from app.services.evolution.approval_service import approval_service
    records = await approval_service.get_records(proposal_id)
    return ApiResponse(success=True, data={"items": records})


# ==================== Promote / Stop ====================

@router.post("/proposals/{proposal_id}/promote", dependencies=[Depends(verify_evolution_access)])
async def promote_proposal(proposal_id: str, user: dict = Depends(verify_evolution_access)):
    """将候选发布为正式版本"""
    from app.services.evolution.promote_service import promote_service
    try:
        receipt = await promote_service.promote(proposal_id, promoted_by=user.get("username", "admin"))
        return ApiResponse(success=True, data=receipt.model_dump(by_alias=True, exclude={"id"}), message="Proposal promoted")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/proposals/{proposal_id}/stop", dependencies=[Depends(verify_evolution_access)])
async def stop_proposal(proposal_id: str, request: StopRequest, user: dict = Depends(verify_evolution_access)):
    """紧急停止提案"""
    from app.services.evolution.promote_service import promote_service
    receipt = await promote_service.stop(proposal_id, request.reason, stopped_by=user.get("username", "admin"))
    return ApiResponse(success=True, data=receipt.model_dump(by_alias=True, exclude={"id"}), message="Proposal stopped")


# ==================== Receipts ====================

@router.get("/receipts", dependencies=[Depends(verify_evolution_access)])
async def list_receipts(skip: int = 0, limit: int = 50):
    """列出自进化回执"""
    from app.services.evolution.receipt_service import receipt_service
    receipts = await receipt_service.list_receipts(skip, limit)
    return ApiResponse(success=True, data={
        "items": [r.model_dump(by_alias=True, exclude={"id"}) for r in receipts],
        "total": len(receipts),
    })


@router.get("/receipts/{receipt_id}", dependencies=[Depends(verify_evolution_access)])
async def get_receipt(receipt_id: str):
    """获取回执详情"""
    from app.services.evolution.receipt_service import receipt_service
    receipt = await receipt_service.get(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return ApiResponse(success=True, data=receipt.model_dump(by_alias=True, exclude={"id"}))


# ==================== Audit Log ====================

@router.get("/audit-log", dependencies=[Depends(verify_evolution_access)])
async def get_audit_log(
    event_type: Optional[str] = None,
    proposal_id: Optional[str] = None,
    artifact_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    """获取自进化事件日志"""
    from app.core.database import get_mongo_db
    db = get_mongo_db()
    query = {}
    if event_type:
        query["event_type"] = event_type
    if proposal_id:
        query["proposal_id"] = proposal_id
    if artifact_id:
        query["artifact_id"] = artifact_id
    cursor = db["evolution_event_log"].find(query).skip(skip).limit(limit).sort("created_at", -1)
    items = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return ApiResponse(success=True, data={"items": items, "total": len(items)})


# ==================== Stats ====================

@router.get("/stats", dependencies=[Depends(verify_evolution_access)])
async def get_stats():
    """获取自进化工作台统计"""
    from app.services.evolution.proposal_service import proposal_service
    from app.services.evolution.receipt_service import receipt_service
    proposal_stats = await proposal_service.get_stats()
    receipt_stats = await receipt_service.get_stats()
    return ApiResponse(success=True, data={
        "proposals": proposal_stats,
        "receipts": receipt_stats,
    })
