"""
个人投资助手 API 路由

提供投资画像、策略管理、策略选股和策略体检功能。
所有接口需要登录认证，并确保用户隔离。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

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


# ==================== 权限检查 ====================

async def get_current_user(request: Request) -> dict:
    """获取当前登录用户（简化版）"""
    # TODO: 实际应该从 JWT token 或 session 中获取
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权访问")

    # 这里返回模拟用户，实际应该验证 token
    return {"id": "user_001", "username": "test_user"}


# ==================== 投资画像 API ====================

@router.get("/profile", dependencies=[Depends(get_current_user)])
async def get_profile(request: Request):
    """获取当前用户的投资画像"""
    user = await get_current_user(request)
    try:
        profile = await profile_service.get_profile(user["id"])
        if not profile:
            return ApiResponse(success=True, data={}, message="画像不存在")
        return ApiResponse(success=True, data=profile)
    except Exception as e:
        logger.error(f"Failed to get profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profile", dependencies=[Depends(get_current_user)])
async def update_profile(request: Request, body: ProfileUpdateRequest):
    """创建或更新投资画像"""
    user = await get_current_user(request)
    try:
        update_data = body.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        profile = await profile_service.create_or_update_profile(user["id"], update_data)
        return ApiResponse(success=True, data=profile, message="画像保存成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/profile", dependencies=[Depends(get_current_user)])
async def delete_profile(request: Request):
    """删除投资画像"""
    user = await get_current_user(request)
    try:
        success = await profile_service.delete_profile(user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Profile not found")
        return ApiResponse(success=True, message="画像已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/summary", dependencies=[Depends(get_current_user)])
async def get_profile_summary(request: Request):
    """获取画像摘要（用于 VibeAgent 上下文注入）"""
    user = await get_current_user(request)
    try:
        summary = await profile_service.get_profile_summary(user["id"])
        if not summary:
            return ApiResponse(success=True, data={}, message="画像不存在")
        return ApiResponse(success=True, data=summary)
    except Exception as e:
        logger.error(f"Failed to get profile summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略管理 API ====================

@router.post("/strategies", dependencies=[Depends(get_current_user)])
async def create_strategy(request: Request, body: StrategyCreateRequest):
    """创建策略"""
    user = await get_current_user(request)
    try:
        result = await strategy_service.create_strategy(
            user_id=user["id"],
            name=body.name,
            description=body.description,
            applicable_markets=body.applicable_markets,
            screening_criteria=body.screening_criteria,
            parameters=body.parameters,
            tags=body.tags,
        )
        return ApiResponse(success=True, data=result, message="策略创建成功")
    except Exception as e:
        logger.error(f"Failed to create strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies", dependencies=[Depends(get_current_user)])
async def list_strategies(
    request: Request,
    include_disabled: bool = False,
    skip: int = 0,
    limit: int = 50,
):
    """列出策略列表"""
    user = await get_current_user(request)
    try:
        strategies = await strategy_service.list_strategies(
            user_id=user["id"],
            include_disabled=include_disabled,
            skip=skip,
            limit=limit,
        )
        return ApiResponse(success=True, data={"items": strategies, "count": len(strategies)})
    except Exception as e:
        logger.error(f"Failed to list strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/{strategy_id}", dependencies=[Depends(get_current_user)])
async def get_strategy(strategy_id: str, request: Request):
    """获取策略详情"""
    user = await get_current_user(request)
    try:
        strategy = await strategy_service.get_strategy(strategy_id, user["id"])
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, data=strategy)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/strategies/{strategy_id}", dependencies=[Depends(get_current_user)])
async def update_strategy(strategy_id: str, request: Request, body: StrategyUpdateRequest):
    """更新策略"""
    user = await get_current_user(request)
    try:
        update_data = body.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        strategy = await strategy_service.update_strategy(strategy_id, user["id"], **update_data)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, data=strategy, message="策略更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategies/{strategy_id}/disable", dependencies=[Depends(get_current_user)])
async def disable_strategy(strategy_id: str, request: Request):
    """停用策略"""
    user = await get_current_user(request)
    try:
        success = await strategy_service.disable_strategy(strategy_id, user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, message="策略已停用")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategies/{strategy_id}/enable", dependencies=[Depends(get_current_user)])
async def enable_strategy(strategy_id: str, request: Request):
    """启用策略"""
    user = await get_current_user(request)
    try:
        success = await strategy_service.enable_strategy(strategy_id, user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return ApiResponse(success=True, message="策略已启用")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略选股 API ====================

@router.post("/screening-tasks", dependencies=[Depends(get_current_user)])
async def create_screening_task(request: Request, body: ScreeningTaskRequest):
    """创建策略选股任务"""
    user = await get_current_user(request)
    try:
        # 验证策略存在且属于当前用户
        strategy = await strategy_service.get_strategy(body.strategy_id, user["id"])
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        result = await task_service.create_task(
            user_id=user["id"],
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


@router.get("/screening-tasks/{task_id}/result", dependencies=[Depends(get_current_user)])
async def get_screening_result(task_id: str, request: Request):
    """获取选股结果"""
    user = await get_current_user(request)
    try:
        # 验证任务属于当前用户
        task = await task_service.get_task(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        result = await task_service.get_screening_result(task_id)
        if not result:
            return ApiResponse(success=True, data={}, message="结果尚未生成")
        return ApiResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get screening result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 策略体检 API ====================

@router.post("/checkup-tasks", dependencies=[Depends(get_current_user)])
async def create_checkup_task(request: Request, body: CheckupTaskRequest):
    """创建策略体检任务"""
    user = await get_current_user(request)
    try:
        # 验证策略存在且属于当前用户
        strategy = await strategy_service.get_strategy(body.strategy_id, user["id"])
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        result = await task_service.create_task(
            user_id=user["id"],
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


@router.get("/checkup-tasks/{task_id}/result", dependencies=[Depends(get_current_user)])
async def get_checkup_result(task_id: str, request: Request):
    """获取体检结果"""
    user = await get_current_user(request)
    try:
        # 验证任务属于当前用户
        task = await task_service.get_task(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        result = await task_service.get_checkup_result(task_id)
        if not result:
            return ApiResponse(success=True, data={}, message="结果尚未生成")
        return ApiResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get checkup result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 任务列表 API ====================

@router.get("/tasks", dependencies=[Depends(get_current_user)])
async def list_tasks(
    request: Request,
    task_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
):
    """列出任务列表"""
    user = await get_current_user(request)
    try:
        type_enum = TaskType(task_type) if task_type else None
        tasks = await task_service.list_tasks(
            user_id=user["id"],
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


@router.get("/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def get_task(task_id: str, request: Request):
    """获取任务详情"""
    user = await get_current_user(request)
    try:
        task = await task_service.get_task(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return ApiResponse(success=True, data=task)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
