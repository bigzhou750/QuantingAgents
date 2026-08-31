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
