"""Agent 决策审计与生产指标路由。"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.routers.auth_db import get_current_user, get_current_admin
from app.services.explainability.audit_service import decision_audit_service
from app.services.explainability.metrics_service import decision_metrics_service

logger = logging.getLogger(__name__)

router = APIRouter()


class ApiResponse(BaseModel):
    success: bool = True
    data: dict = {}
    message: str = ""


class ReviewUpdateRequest(BaseModel):
    action: str = Field(..., description="复核动作: approve/reject/adjust")
    reviewer: str = Field(..., description="复核人")
    reason: str = Field(default="", description="复核原因")


async def verify_decision_audit_enabled():
    if not settings.DECISION_AUDIT_ENABLED:
        raise HTTPException(status_code=403, detail="决策审计能力未启用")


@router.get(
    "/chains/{identifier}",
    dependencies=[Depends(verify_decision_audit_enabled)],
)
async def get_decision_audit_chain(
    identifier: str,
    user: dict = Depends(get_current_user),
):
    """按 business_id/task_id/session_id/trial_id 查询统一审计链。"""
    try:
        audit = await decision_audit_service.build_audit(identifier, user)
        return ApiResponse(data=audit, message="决策审计链已生成")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("failed to build decision audit chain")
        raise HTTPException(status_code=500, detail=f"构建决策审计链失败: {exc}")


@router.get("/metrics", dependencies=[Depends(get_current_admin)])
async def list_decision_metrics(
    limit: int = 30,
):
    """管理员查看生产决策链指标。"""
    try:
        metrics = await decision_metrics_service.get_recent_metrics(limit=min(limit, 200))
        return ApiResponse(data={"items": metrics, "count": len(metrics)}, message="指标已返回")
    except Exception as exc:
        logger.exception("failed to list decision metrics")
        raise HTTPException(status_code=500, detail=f"读取决策指标失败: {exc}")


@router.get("/alerts", dependencies=[Depends(get_current_admin)])
async def check_decision_alerts():
    """管理员检查当前决策链指标告警。"""
    try:
        metrics = await decision_metrics_service.get_recent_metrics(limit=30)
        alerts = []
        for metric in metrics:
            alerts.extend(decision_metrics_service.check_alerts(metric))
        await decision_metrics_service.publish_alerts(alerts)
        return ApiResponse(data={"alerts": alerts, "count": len(alerts)}, message="告警检查完成")
    except Exception as exc:
        logger.exception("failed to check decision alerts")
        raise HTTPException(status_code=500, detail=f"告警检查失败: {exc}")


@router.post("/reviews/{review_id}", dependencies=[Depends(get_current_admin)])
async def update_decision_review(
    review_id: str,
    payload: ReviewUpdateRequest,
):
    """管理员更新决策人工复核结果。"""
    try:
        review = await decision_audit_service.update_review_status(
            review_id,
            payload.reviewer,
            payload.action,
            payload.reason,
        )
        if not review:
            raise HTTPException(status_code=404, detail="复核记录不存在")
        return ApiResponse(data=review, message="复核结果已更新")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("failed to update decision review")
        raise HTTPException(status_code=500, detail=f"更新复核结果失败: {exc}")
