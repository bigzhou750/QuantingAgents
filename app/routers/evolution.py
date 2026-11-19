"""
Agent 自进化闭环 API 路由

提供 artifact 注册、候选提案管理、验证运行、审批、promote/rollback、
回执查询和审计日志等功能。仅允许管理员访问。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
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
    request_id: str = ""
    idempotency_key: str = ""
    environment: str = "default"


class ApprovalRequest(BaseModel):
    comment: str = ""
    request_id: str = ""
    idempotency_key: str = ""


class StopRequest(BaseModel):
    reason: str = "manual"
    request_id: str = ""
    idempotency_key: str = ""


class PostReleaseObservationRequest(BaseModel):
    """发布后质量观测请求"""
    receipt_id: str
    metrics: dict


class OnlineBadcaseConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    enable_judge: Optional[bool] = None
    soft_sample_rate: Optional[float] = None
    confidence_threshold: Optional[float] = None
    judge_threshold: Optional[float] = None
    evidence_threshold: Optional[float] = None
    max_content_length: Optional[int] = None
    change_reason: str = ""


class OnlineBadcaseConfigPublishRequest(BaseModel):
    change_reason: str = ""


class EvolutionConfigUpdate(BaseModel):
    automation_mode: Optional[str] = None
    trigger_regression_threshold: Optional[float] = None
    trigger_bad_case_count: Optional[int] = None
    budget_max_runs_per_day: Optional[int] = None
    human_gate: Optional[bool] = None
    schedule_cron: Optional[str] = None
    cooldown_minutes: Optional[int] = None
    change_budget_chars: Optional[int] = None
    daily_cost_budget_usd: Optional[float] = None
    require_smoke_test: Optional[bool] = None


# ==================== 权限检查 ====================

async def verify_evolution_access(current_user: dict = Depends(get_current_user)) -> dict:
    """验证自进化平台访问权限"""
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="仅管理员可访问自进化平台")
    return current_user


# ==================== Health & Config ====================

@router.get("/health", dependencies=[Depends(verify_evolution_access)])
async def health_check():
    """健康检查"""
    return ApiResponse(success=True, data={"status": "ok", "enabled": True})


@router.get("/config", dependencies=[Depends(verify_evolution_access)])
async def get_config():
    """获取自进化配置"""
    data = {
        "enabled": True,
        "automation_mode": settings.EVOLUTION_AUTOMATION_MODE,
        "trigger_regression_threshold": settings.EVOLUTION_TRIGGER_REGRESSION_THRESHOLD,
        "trigger_bad_case_count": settings.EVOLUTION_TRIGGER_BAD_CASE_COUNT,
        "budget_max_runs_per_day": settings.EVOLUTION_BUDGET_MAX_RUNS_PER_DAY,
        "human_gate": settings.EVOLUTION_HUMAN_GATE,
        "allowed_artifact_types": settings.EVOLUTION_ALLOWED_ARTIFACT_TYPES,
        "schedule_cron": settings.EVOLUTION_SCHEDULE_CRON,
    }
    from app.services.evolution.governance_service import governance_service
    data["governance"] = await governance_service.get_config()
    return ApiResponse(success=True, data=data)


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
    governance_values = update.model_dump(exclude_none=True)
    governance_values = {
        key: governance_values[key]
        for key in ("cooldown_minutes", "change_budget_chars", "daily_cost_budget_usd", "require_smoke_test")
        if key in governance_values
    }
    if governance_values:
        from app.services.evolution.governance_service import governance_service
        updated["governance"] = await governance_service.update_config(governance_values)
    return ApiResponse(success=True, data=updated, message="配置已更新")


# ==================== 线上 Bad Case 配置 ====================

@router.get("/online-badcase-config", dependencies=[Depends(verify_evolution_access)])
async def get_online_badcase_config():
    """查看当前生效配置和历史版本。"""
    from app.services.eval.online_badcase_config_service import (
        online_badcase_config_service,
    )

    effective = await online_badcase_config_service.get_effective_config()
    history = await online_badcase_config_service.list_configs()
    return ApiResponse(
        success=True,
        data={"effective": effective, "history": history},
        message="线上 Bad Case 配置已返回",
    )


@router.post("/online-badcase-config/drafts", dependencies=[Depends(verify_evolution_access)])
async def create_online_badcase_draft(
    payload: OnlineBadcaseConfigUpdate,
    user: dict = Depends(verify_evolution_access),
):
    """创建未发布配置草稿。"""
    from app.services.eval.online_badcase_config_service import (
        online_badcase_config_service,
    )

    try:
        data = {
            "enabled": payload.enabled if payload.enabled is not None else False,
            "enable_judge": payload.enable_judge if payload.enable_judge is not None else False,
            "soft_sample_rate": payload.soft_sample_rate if payload.soft_sample_rate is not None else 0.1,
            "confidence_threshold": payload.confidence_threshold if payload.confidence_threshold is not None else 0.8,
            "judge_threshold": payload.judge_threshold if payload.judge_threshold is not None else 0.6,
            "evidence_threshold": payload.evidence_threshold if payload.evidence_threshold is not None else 0.6,
            "max_content_length": payload.max_content_length if payload.max_content_length is not None else 5000,
            "change_reason": payload.change_reason,
        }
        draft = await online_badcase_config_service.create_draft(
            data,
            updated_by=str(user.get("username") or user.get("id") or "admin"),
        )
        return ApiResponse(success=True, data=draft, message="草稿已创建")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/online-badcase-config/{config_id}/publish",
    dependencies=[Depends(verify_evolution_access)],
)
async def publish_online_badcase_config(
    config_id: str,
    payload: OnlineBadcaseConfigPublishRequest,
    user: dict = Depends(verify_evolution_access),
):
    """发布配置并让运行时读取。"""
    from app.services.eval.online_badcase_config_service import (
        online_badcase_config_service,
    )

    try:
        published = await online_badcase_config_service.publish(
            config_id,
            updated_by=str(user.get("username") or user.get("id") or "admin"),
            change_reason=payload.change_reason,
        )
        return ApiResponse(success=True, data=published, message="配置已发布")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/online-badcase-config/{config_id}/rollback",
    dependencies=[Depends(verify_evolution_access)],
)
async def rollback_online_badcase_config(
    config_id: str,
    payload: OnlineBadcaseConfigPublishRequest,
    user: dict = Depends(verify_evolution_access),
):
    """回滚到指定历史有效配置。"""
    from app.services.eval.online_badcase_config_service import (
        online_badcase_config_service,
    )

    try:
        rolled_back = await online_badcase_config_service.rollback(
            config_id,
            updated_by=str(user.get("username") or user.get("id") or "admin"),
            change_reason=payload.change_reason,
        )
        return ApiResponse(success=True, data=rolled_back, message="配置已回滚")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@router.get("/artifacts/{artifact_id}/release-history", dependencies=[Depends(verify_evolution_access)])
async def get_artifact_release_history(artifact_id: str, skip: int = 0, limit: int = 50):
    """查看 artifact 的版本历史、当前生效状态和发布/回滚回执。"""
    from app.services.evolution.artifact_registry import artifact_registry
    from app.services.evolution.receipt_service import receipt_service

    entry = await artifact_registry.get_registry_entry(artifact_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Artifact not found")
    versions = await artifact_registry.list_versions(artifact_id, skip, limit)
    receipts = await receipt_service.list_by_artifact(artifact_id, skip, limit)
    return ApiResponse(success=True, data={
        "artifact": entry.model_dump(by_alias=True, exclude={"id"}),
        "versions": [v.model_dump(by_alias=True, exclude={"id"}) for v in versions],
        "receipts": [r.model_dump(by_alias=True, exclude={"id"}) for r in receipts],
    })


@router.post("/artifacts/{artifact_id}/rollback", dependencies=[Depends(verify_evolution_access)])
async def rollback_artifact(artifact_id: str, request: RollbackRequest, user: dict = Depends(verify_evolution_access)):
    """回滚 artifact 到指定版本"""
    from app.services.evolution.promote_service import promote_service
    try:
        receipt = await promote_service.rollback(
            artifact_id,
            request.target_version,
            rolled_back_by=user["username"],
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            environment=request.environment,
        )
        return ApiResponse(success=True, data=receipt.model_dump(by_alias=True, exclude={"id"}), message=f"Rolled back to {request.target_version}")
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
    record = await approval_service.approve(
        proposal_id,
        user["username"],
        request.comment,
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
    )
    return ApiResponse(success=True, data=record, message="Proposal approved")


@router.post("/proposals/{proposal_id}/reject", dependencies=[Depends(verify_evolution_access)])
async def reject_proposal(proposal_id: str, request: ApprovalRequest, user: dict = Depends(verify_evolution_access)):
    """拒绝提案"""
    from app.services.evolution.approval_service import approval_service
    record = await approval_service.reject(
        proposal_id,
        user["username"],
        request.comment,
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
    )
    return ApiResponse(success=True, data=record, message="Proposal rejected")


@router.post("/proposals/{proposal_id}/comment", dependencies=[Depends(verify_evolution_access)])
async def comment_proposal(proposal_id: str, request: ApprovalRequest, user: dict = Depends(verify_evolution_access)):
    """添加评论"""
    from app.services.evolution.approval_service import approval_service
    record = await approval_service.comment(
        proposal_id,
        user["username"],
        request.comment,
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
    )
    return ApiResponse(success=True, data=record, message="Comment added")


@router.get("/proposals/{proposal_id}/audit", dependencies=[Depends(verify_evolution_access)])
async def get_audit_trail(proposal_id: str):
    """获取审批审计记录"""
    from app.services.evolution.approval_service import approval_service
    records = await approval_service.get_records(proposal_id)
    return ApiResponse(success=True, data={"items": records})


# ==================== Promote / Stop ====================

@router.post("/proposals/{proposal_id}/promote", dependencies=[Depends(verify_evolution_access)])
async def promote_proposal(
    proposal_id: str,
    request_id: Optional[str] = Query(None),
    idempotency_key: Optional[str] = Query(None),
    environment: str = Query("default"),
    allow_skill_regression_override: bool = Query(False),
    user: dict = Depends(verify_evolution_access),
):
    """将候选发布为正式版本"""
    from app.services.evolution.promote_service import promote_service
    try:
        receipt = await promote_service.promote(
            proposal_id,
            promoted_by=user["username"],
            request_id=request_id or "",
            idempotency_key=idempotency_key or "",
            environment=environment,
            allow_skill_regression_override=allow_skill_regression_override,
        )
        return ApiResponse(success=True, data=receipt.model_dump(by_alias=True, exclude={"id"}), message="Proposal promoted")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/proposals/{proposal_id}/stop", dependencies=[Depends(verify_evolution_access)])
async def stop_proposal(proposal_id: str, request: StopRequest, user: dict = Depends(verify_evolution_access)):
    """紧急停止提案"""
    from app.services.evolution.promote_service import promote_service
    receipt = await promote_service.stop(
        proposal_id,
        request.reason,
        stopped_by=user["username"],
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
    )
    return ApiResponse(success=True, data=receipt.model_dump(by_alias=True, exclude={"id"}), message="Proposal stopped")


# ==================== Receipts ====================

@router.post("/post-release/observe", dependencies=[Depends(verify_evolution_access)])
async def observe_post_release(request: PostReleaseObservationRequest):
    """判断发布后指标是否退化，并返回回滚建议。"""
    from app.services.evolution.receipt_service import receipt_service
    from app.services.evolution.governance_service import governance_service
    receipt = await receipt_service.get(request.receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    result = await governance_service.route_post_release_observation(receipt, request.metrics)
    if result["rollback_suggestion"]:
        result["suggested_rollback"] = {
            "artifact_id": receipt.artifact_id,
            "target_version": receipt.baseline_artifact_version,
        }
    return ApiResponse(success=True, data=result, message="发布后观测完成")


@router.get("/follow-up-actions", dependencies=[Depends(verify_evolution_access)])
async def list_follow_up_actions(
    artifact_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    """查看自进化自动回流产生的后续动作候选。"""
    from app.services.evolution.governance_service import governance_service

    items = await governance_service.list_follow_up_actions(artifact_id, status, skip, limit)
    return ApiResponse(success=True, data={"items": items, "total": len(items)})


@router.post("/notifications/retry", dependencies=[Depends(verify_evolution_access)])
async def retry_evolution_notifications():
    """重试失败的自进化通知投递。"""
    from app.services.evolution.governance_service import governance_service
    result = await governance_service.retry_failed_notifications()
    return ApiResponse(success=True, data=result, message="通知重试完成")


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
