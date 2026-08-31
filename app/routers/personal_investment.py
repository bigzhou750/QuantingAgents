"""
个人投资助手 API 路由

提供投资画像、策略管理、策略选股和策略体检功能。
所有接口需要登录认证，并确保用户隔离。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth_db import get_current_user
from app.services.personal_investment.profile_service import profile_service
from app.services.personal_investment.strategy_service import strategy_service
from app.services.personal_investment.task_service import task_service
from app.models.personal_investment import TaskType

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 请求/响应模型 ====================

class ApiResponse(BaseModel):
    success: bool = True
    data: dict = {}
    message: str = ""


class ProfileUpdateRequest(BaseModel):
    risk_preference: Optional[str] = None
    trading_style: Optional[str] = None
    capital_range_min: Optional[float] = None
    capital_range_max: Optional[float] = None
    target_markets: Optional[List[str]] = None
    excluded_sectors: Optional[List[str]] = None
    excluded_stocks: Optional[List[str]] = None
    exclude_st: Optional[bool] = None
    exclude_new_stock_days: Optional[int] = None
    current_holdings: Optional[List[dict]] = None
    max_position_per_stock: Optional[float] = None
    default_context: Optional[str] = None
    context_injection_enabled: Optional[bool] = None


class StrategyCreateRequest(BaseModel):
    name: str
    description: str = ""
    applicable_markets: List[str] = ["A股"]
    screening_criteria: dict = {}
    parameters: dict = {}
    tags: List[str] = []


class StrategyUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    applicable_markets: Optional[List[str]] = None
    screening_criteria: Optional[dict] = None
    parameters: Optional[dict] = None
    tags: Optional[List[str]] = None


class ScreeningTaskRequest(BaseModel):
    strategy_id: str
    profile_id: Optional[str] = None
    params: dict = {}


class CheckupTaskRequest(BaseModel):
    strategy_id: str
    profile_id: Optional[str] = None
    params: dict = {}


# ==================== 投资画像 API ====================

@router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """获取当前用户的投资画像"""
    try:
        profile = await profile_service.get_profile(current_user["id"])
        if not profile:
            return ApiResponse(success=True, data={}, message="画像不存在")
        return ApiResponse(success=True, data=profile)
    except Exception as e:
        logger.error(f"Failed to get profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profile")
async def update_profile(body: ProfileUpdateRequest, current_user: dict = Depends(get_current_user)):
    """创建或更新投资画像"""
    try:
        update_data = body.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        profile = await profile_service.create_or_update_profile(current_user["id"], update_data)
        return ApiResponse(success=True, data=profile, message="画像保存成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/profile")
async def delete_profile(current_user: dict = Depends(get_current_user)):
    """删除投资画像"""
    try:
        success = await profile_service.delete_profile(current_user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Profile not found")
        return ApiResponse(success=True, message="画像已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/summary")
async def get_profile_summary(current_user: dict = Depends(get_current_user)):
    """获取画像摘要（用于 VibeAgent 上下文注入）"""
    try:
        summary = await profile_service.get_profile_summary(current_user["id"])
        if not summary:
            return ApiResponse(success=True, data={}, message="画像不存在")
        return ApiResponse(success=True, data=summary)
    except Exception as e:
        logger.error(f"Failed to get profile summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略管理 API ====================

@router.post("/strategies")
async def create_strategy(body: StrategyCreateRequest, current_user: dict = Depends(get_current_user)):
    """创建策略"""
    try:
        result = await strategy_service.create_strategy(
            user_id=current_user["id"],
            name=body.name,
            description=body.description,
            applicable_markets=body.applicable_markets,
            screening_criteria=body.screening_criteria,
            parameters=body.parameters,
            tags=body.tags,
        )
        return ApiResponse(success=True, data=result, message="策略创建成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def list_strategies(
    include_disabled: bool = False,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """列出策略列表"""
    try:
        strategies = await strategy_service.list_strategies(
            user_id=current_user["id"],
            include_disabled=include_disabled,
            skip=skip,
            limit=limit,
        )
        return ApiResponse(success=True, data={"items": strategies, "count": len(strategies)})
    except Exception as e:
        logger.error(f"Failed to list strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str, current_user: dict = Depends(get_current_user)):
    """获取策略详情"""
    try:
        strategy = await strategy_service.get_strategy(strategy_id, current_user["id"])
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, data=strategy)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, body: StrategyUpdateRequest, current_user: dict = Depends(get_current_user)):
    """更新策略"""
    try:
        update_data = body.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        strategy = await strategy_service.update_strategy(strategy_id, current_user["id"], **update_data)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, data=strategy, message="策略更新成功")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategies/{strategy_id}/disable")
async def disable_strategy(strategy_id: str, current_user: dict = Depends(get_current_user)):
    """停用策略"""
    try:
        success = await strategy_service.disable_strategy(strategy_id, current_user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, message="策略已停用")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategies/{strategy_id}/enable")
async def enable_strategy(strategy_id: str, current_user: dict = Depends(get_current_user)):
    """启用策略"""
    try:
        success = await strategy_service.enable_strategy(strategy_id, current_user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, message="策略已启用")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略选股 API ====================

@router.post("/screening-tasks")
async def create_screening_task(body: ScreeningTaskRequest, current_user: dict = Depends(get_current_user)):
    """创建策略选股任务"""
    try:
        # 验证策略存在且属于当前用户
        strategy = await strategy_service.get_strategy(body.strategy_id, current_user["id"])
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        result = await task_service.create_task(
            user_id=current_user["id"],
            task_type=TaskType.STRATEGY_SCREENING,
            strategy_id=body.strategy_id,
            profile_id=body.profile_id,
            input_params=body.params,
        )
        return ApiResponse(success=True, data=result, message="选股任务已创建")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create screening task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screening-tasks/{task_id}/result")
async def get_screening_result(task_id: str, current_user: dict = Depends(get_current_user)):
    """获取选股结果"""
    try:
        # 验证任务属于当前用户
        task = await task_service.get_task(task_id, current_user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        result = await task_service.get_screening_result(task_id)
        if not result:
            return ApiResponse(success=True, data={}, message="结果尚未生成")
        result["strategy_id"] = task.get("strategy_id")
        result["profile_id"] = task.get("profile_id")
        result["data_sources"] = task.get("data_sources", [])
        result["data_as_of"] = task.get("data_as_of")
        result["task_status"] = task.get("status")
        return ApiResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get screening result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略体检 API ====================

@router.post("/checkup-tasks")
async def create_checkup_task(body: CheckupTaskRequest, current_user: dict = Depends(get_current_user)):
    """创建策略体检任务"""
    try:
        # 验证策略存在且属于当前用户
        strategy = await strategy_service.get_strategy(body.strategy_id, current_user["id"])
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        result = await task_service.create_task(
            user_id=current_user["id"],
            task_type=TaskType.STRATEGY_CHECKUP,
            strategy_id=body.strategy_id,
            profile_id=body.profile_id,
            input_params=body.params,
        )
        return ApiResponse(success=True, data=result, message="体检任务已创建")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create checkup task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checkup-tasks/{task_id}/result")
async def get_checkup_result(task_id: str, current_user: dict = Depends(get_current_user)):
    """获取体检结果"""
    try:
        # 验证任务属于当前用户
        task = await task_service.get_task(task_id, current_user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        result = await task_service.get_checkup_result(task_id)
        if not result:
            return ApiResponse(success=True, data={}, message="结果尚未生成")
        result["strategy_id"] = task.get("strategy_id")
        result["profile_id"] = task.get("profile_id")
        result["data_sources"] = task.get("data_sources", [])
        result["data_as_of"] = task.get("data_as_of")
        result["task_status"] = task.get("status")
        return ApiResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get checkup result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 任务列表 API ====================

@router.get("/tasks")
async def list_tasks(
    task_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """列出任务列表"""
    try:
        type_enum = TaskType(task_type) if task_type else None
        tasks = await task_service.list_tasks(
            user_id=current_user["id"],
            task_type=type_enum,
            skip=skip,
            limit=limit,
        )
        return ApiResponse(success=True, data={"items": tasks, "count": len(tasks)})
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_type}")
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """获取任务详情"""
    try:
        task = await task_service.get_task(task_id, current_user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return ApiResponse(success=True, data=task)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 首页聚合摘要 ====================

@router.get("/home-summary")
async def get_home_summary(current_user: dict = Depends(get_current_user)):
    """个人投资助手首页聚合摘要

    返回当前用户的画像、策略、任务、观察和模拟持仓摘要。
    每个模块独立 try-catch，支持局部失败降级。
    """
    user_id = current_user["id"]
    user_name = current_user.get("name", current_user.get("username", "投资者"))
    result: dict = {"user_name": user_name, "errors": {}}

    # 1. 画像摘要
    try:
        profile = await profile_service.get_profile(user_id)
        if profile:
            result["profile"] = {
                "exists": True,
                "risk_preference": profile.get("risk_preference", ""),
                "trading_style": profile.get("trading_style", ""),
                "target_markets": profile.get("target_markets", []),
            }
        else:
            result["profile"] = {"exists": False}
    except Exception as e:
        logger.warning(f"[HomeSummary] Profile fetch failed for {user_id}: {e}")
        result["profile"] = {"exists": False}
        result["errors"]["profile"] = str(e)

    # 2. 策略摘要
    try:
        strategies = await strategy_service.list_strategies(user_id, include_disabled=False, skip=0, limit=5)
        items = strategies.get("items", []) if isinstance(strategies, dict) else []
        active_count = len(items)
        result["strategies"] = {
            "active_count": active_count,
            "recent": [
                {"strategy_id": s.get("strategy_id"), "name": s.get("name"), "status": s.get("status")}
                for s in items[:3]
            ],
        }
    except Exception as e:
        logger.warning(f"[HomeSummary] Strategies fetch failed for {user_id}: {e}")
        result["strategies"] = {"active_count": 0, "recent": []}
        result["errors"]["strategies"] = str(e)

    # 3. 最近任务
    try:
        tasks = await task_service.list_tasks(user_id, skip=0, limit=5)
        task_items = tasks.get("items", []) if isinstance(tasks, dict) else []
        result["tasks"] = {
            "recent": [
                {
                    "task_id": t.get("task_id"),
                    "task_type": t.get("task_type"),
                    "status": t.get("status"),
                    "created_at": t.get("created_at"),
                }
                for t in task_items[:5]
            ]
        }
    except Exception as e:
        logger.warning(f"[HomeSummary] Tasks fetch failed for {user_id}: {e}")
        result["tasks"] = {"recent": []}
        result["errors"]["tasks"] = str(e)

    # 4. 模拟持仓摘要
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        account = await db["paper_accounts"].find_one({"user_id": user_id})
        positions_cursor = db["paper_positions"].find({"user_id": user_id, "quantity": {"$gt": 0}})
        position_count = await db["paper_positions"].count_documents({"user_id": user_id, "quantity": {"$gt": 0}})

        if account:
            total_equity = 0
            unrealized_pnl = 0
            for currency_data in account.get("equity", {}).values():
                if isinstance(currency_data, dict):
                    total_equity += currency_data.get("total", 0)
            for currency_data in account.get("unrealized_pnl", {}).values():
                if isinstance(currency_data, dict):
                    unrealized_pnl += currency_data.get("total", 0)

            result["simulation"] = {
                "has_positions": position_count > 0,
                "position_count": position_count,
                "total_equity": total_equity,
                "unrealized_pnl": unrealized_pnl,
            }
        else:
            result["simulation"] = {"has_positions": False, "position_count": 0}
    except Exception as e:
        logger.warning(f"[HomeSummary] Simulation fetch failed for {user_id}: {e}")
        result["simulation"] = {"has_positions": False, "position_count": 0}
        result["errors"]["simulation"] = str(e)

    # 5. 观察标的摘要（真实观察集合 + 待复盘计数）
    try:
        obs_data = await observation_service.list_observations(user_id, status="active", skip=0, limit=1)
        pending = await observation_service.get_pending_reviews(user_id)
        items = obs_data.get("items", [])
        latest_item = items[0] if items else None
        result["observations"] = {
            "count": obs_data.get("total", 0),
            "pending_review_count": pending.get("count", 0),
            "latest_item": {
                "stock_code": latest_item.get("stock_code", ""),
                "stock_name": latest_item.get("stock_name", ""),
                "source_type": latest_item.get("source_type", ""),
                "created_at": latest_item.get("created_at"),
            } if latest_item else None,
        }
    except Exception as e:
        logger.warning(f"[HomeSummary] Observations fetch failed for {user_id}: {e}")
        result["observations"] = {"count": 0, "pending_review_count": 0, "latest_item": None}
        result["errors"]["observations"] = str(e)

    # 清理空 errors
    if not result["errors"]:
        del result["errors"]

    return ApiResponse(success=True, data=result)


# ==================== 策略广场 API ====================

@router.get("/marketplace")
async def list_marketplace_templates(
    tag: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """列出策略广场已上架的策略模板"""
    try:
        from app.services.personal_investment.marketplace_service import marketplace_service
        result = await marketplace_service.list_published_templates(tag=tag, skip=skip, limit=limit)
        return ApiResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"Failed to list marketplace templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/marketplace/{template_id}")
async def get_marketplace_template(template_id: str, current_user: dict = Depends(get_current_user)):
    """获取策略模板详情"""
    try:
        from app.services.personal_investment.marketplace_service import marketplace_service
        template = await marketplace_service.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Strategy template not found")
        if template.get("status") != "published":
            raise HTTPException(status_code=403, detail="该策略模板未上架")
        return ApiResponse(success=True, data=template)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get marketplace template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marketplace/{template_id}/adopt")
async def adopt_template(template_id: str, current_user: dict = Depends(get_current_user)):
    """将策略模板加入我的策略"""
    try:
        from app.services.personal_investment.marketplace_service import marketplace_service
        result = await marketplace_service.adopt_template(template_id, current_user["id"])
        return ApiResponse(success=True, data=result, message="策略已加入你的策略列表")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to adopt template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 观察标的 API ====================

from app.models.observation import (
    AddObservationRequest,
    UpdateObservationRequest,
    AddReviewNoteRequest,
    ObservationRecord,
)
from app.services.personal_investment.observation_service import observation_service


@router.get("/observations/review-summary")
async def get_review_summary(current_user: dict = Depends(get_current_user)):
    """获取待复盘汇总"""
    try:
        result = await observation_service.get_pending_reviews(current_user["id"])
        return ApiResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"Failed to get review summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/observations")
async def list_observations(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """列出观察标的"""
    try:
        result = await observation_service.list_observations(
            user_id=current_user["id"],
            status=status,
            skip=skip,
            limit=limit,
        )
        return ApiResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"Failed to list observations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/observations")
async def add_observation(body: AddObservationRequest, current_user: dict = Depends(get_current_user)):
    """添加观察标的"""
    try:
        record = ObservationRecord(
            user_id=current_user["id"],
            stock_code=body.stock_code,
            stock_name=body.stock_name,
            market=body.market,
            source_type=body.source_type,
            source_strategy_id=body.source_strategy_id,
            source_task_id=body.source_task_id,
            match_reasons=body.match_reasons,
            risk_warnings=body.risk_warnings,
            user_notes=body.user_notes,
        )
        result = await observation_service.add_observation(current_user["id"], record)
        return ApiResponse(success=True, data=result, message="已加入观察")
    except Exception as e:
        logger.error(f"Failed to add observation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/observations/{observation_id}")
async def get_observation(observation_id: str, current_user: dict = Depends(get_current_user)):
    """获取观察标的详情"""
    try:
        result = await observation_service.get_observation(observation_id, current_user["id"])
        if not result:
            raise HTTPException(status_code=404, detail="Observation not found")
        return ApiResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get observation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/observations/{observation_id}")
async def update_observation(
    observation_id: str,
    body: UpdateObservationRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新观察标的备注"""
    try:
        update_data = body.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = await observation_service.update_observation(
            observation_id, current_user["id"], **update_data
        )
        if not result:
            raise HTTPException(status_code=404, detail="Observation not found")
        return ApiResponse(success=True, data=result, message="更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update observation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/observations/{observation_id}/remove")
async def remove_observation(observation_id: str, current_user: dict = Depends(get_current_user)):
    """移出观察标的（状态更新，不删除）"""
    try:
        success = await observation_service.remove_observation(observation_id, current_user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Observation not found")
        return ApiResponse(success=True, message="已移出观察")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove observation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/observations/{observation_id}/review")
async def add_review_note(
    observation_id: str,
    body: AddReviewNoteRequest,
    current_user: dict = Depends(get_current_user),
):
    """添加复盘备注"""
    try:
        # 验证观察标的存在且属于当前用户
        obs = await observation_service.get_observation(observation_id, current_user["id"])
        if not obs:
            raise HTTPException(status_code=404, detail="Observation not found")

        result = await observation_service.add_review_note(
            user_id=current_user["id"],
            target_id=observation_id,
            content=body.content,
            target_type=body.target_type,
        )
        return ApiResponse(success=True, data=result, message="复盘备注已保存")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add review note: {e}")
        raise HTTPException(status_code=500, detail=str(e))
