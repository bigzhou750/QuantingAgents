"""
Agent 评测平台 API 路由

提供评测集管理、评测运行、trial 查询、trace 回放和评分复核等功能。
仅允许研发和管理员角色访问。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings
from app.services.eval.dataset_service import dataset_service
from app.services.eval.runner_service import runner_service
from app.services.eval.trace_adapter import trace_adapter
from app.services.eval.scorer_hub import scorer_hub

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 请求/响应模型 ====================

class ApiResponse(BaseModel):
    success: bool = True
    data: dict = {}
    message: str = ""


class DatasetCreateRequest(BaseModel):
    name: str
    description: str = ""
    tags: List[str] = []


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None


class CaseCreateRequest(BaseModel):
    name: str
    input: dict
    expected_output: Optional[dict] = None
    scoring_criteria: Optional[dict] = None
    tags: List[str] = []
    difficulty: str = "medium"
    category: str = "general"
    description: str = ""


class CaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input: Optional[dict] = None
    expected_output: Optional[dict] = None
    scoring_criteria: Optional[dict] = None
    tags: Optional[List[str]] = None
    difficulty: Optional[str] = None
    category: Optional[str] = None


class RunCreateRequest(BaseModel):
    dataset_id: str
    dataset_version: Optional[str] = None
    num_trials: int = 1
    config: dict = {}


# ==================== 权限检查 ====================

async def verify_eval_access(request: Request):
    """验证评测平台访问权限"""
    # 首先检查功能开关
    if not settings.EVAL_PLATFORM_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Agent 评测平台未启用，请联系管理员开启 EVAL_PLATFORM_ENABLED 配置"
        )

    # TODO: 验证用户角色（研发/管理员）
    # 目前先通过 Authorization header 验证登录状态
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权访问")

    return True


# ==================== 健康检查 ====================

@router.get("/health")
async def eval_health():
    """评测平台健康检查"""
    return {
        "status": "ok",
        "enabled": settings.EVAL_PLATFORM_ENABLED,
        "version": "1.0.0-mvp",
    }


# ==================== 评测集 API ====================

@router.post("/datasets", dependencies=[Depends(verify_eval_access)])
async def create_dataset(request: DatasetCreateRequest):
    """创建评测集"""
    try:
        result = await dataset_service.create_dataset(
            name=request.name,
            description=request.description,
            tags=request.tags,
        )
        return ApiResponse(success=True, data=result, message="评测集创建成功")
    except Exception as e:
        logger.error(f"Failed to create dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets", dependencies=[Depends(verify_eval_access)])
async def list_datasets(
    skip: int = 0,
    limit: int = 20,
    tags: Optional[str] = None,
    status: Optional[str] = None,
):
    """列出评测集"""
    try:
        tag_list = tags.split(",") if tags else None
        datasets = await dataset_service.list_datasets(
            skip=skip,
            limit=limit,
            tags=tag_list,
            status=status,
        )
        return ApiResponse(success=True, data={"items": datasets, "count": len(datasets)})
    except Exception as e:
        logger.error(f"Failed to list datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}", dependencies=[Depends(verify_eval_access)])
async def get_dataset(dataset_id: str, include_cases: bool = False):
    """获取评测集详情"""
    try:
        if include_cases:
            dataset = await dataset_service.get_dataset_with_cases(dataset_id)
        else:
            dataset = await dataset_service.get_dataset(dataset_id)

        if not dataset:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

        return ApiResponse(success=True, data=dataset)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/datasets/{dataset_id}", dependencies=[Depends(verify_eval_access)])
async def update_dataset(dataset_id: str, request: DatasetUpdateRequest):
    """更新评测集"""
    try:
        result = await dataset_service.update_dataset(
            dataset_id=dataset_id,
            name=request.name,
            description=request.description,
            tags=request.tags,
            status=request.status,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

        return ApiResponse(success=True, data=result, message="评测集更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/datasets/{dataset_id}", dependencies=[Depends(verify_eval_access)])
async def delete_dataset(dataset_id: str):
    """删除评测集（软删除）"""
    try:
        success = await dataset_service.delete_dataset(dataset_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

        return ApiResponse(success=True, message="评测集已归档")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 评测用例 API ====================

@router.post("/datasets/{dataset_id}/cases", dependencies=[Depends(verify_eval_access)])
async def add_case(dataset_id: str, request: CaseCreateRequest):
    """向评测集添加用例"""
    try:
        result = await dataset_service.add_case(
            dataset_id=dataset_id,
            name=request.name,
            input_data=request.input,
            expected_output=request.expected_output,
            scoring_criteria=request.scoring_criteria,
            tags=request.tags,
            difficulty=request.difficulty,
            category=request.category,
            description=request.description,
        )
        return ApiResponse(success=True, data=result, message="用例添加成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}/cases", dependencies=[Depends(verify_eval_access)])
async def list_cases(
    dataset_id: str,
    skip: int = 0,
    limit: int = 50,
    tags: Optional[str] = None,
    category: Optional[str] = None,
):
    """列出评测集中的用例"""
    try:
        tag_list = tags.split(",") if tags else None
        cases = await dataset_service.list_cases(
            dataset_id=dataset_id,
            skip=skip,
            limit=limit,
            tags=tag_list,
            category=category,
        )
        return ApiResponse(success=True, data={"items": cases, "count": len(cases)})
    except Exception as e:
        logger.error(f"Failed to list cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}", dependencies=[Depends(verify_eval_access)])
async def get_case(case_id: str):
    """获取用例详情"""
    try:
        case = await dataset_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        return ApiResponse(success=True, data=case)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/cases/{case_id}", dependencies=[Depends(verify_eval_access)])
async def update_case(case_id: str, request: CaseUpdateRequest):
    """更新用例"""
    try:
        update_data = request.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = await dataset_service.update_case(case_id, **update_data)
        if not result:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        return ApiResponse(success=True, data=result, message="用例更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cases/{case_id}", dependencies=[Depends(verify_eval_access)])
async def delete_case(case_id: str):
    """删除用例"""
    try:
        success = await dataset_service.delete_case(case_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        return ApiResponse(success=True, message="用例删除成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 评测运行 API ====================

@router.post("/runs", dependencies=[Depends(verify_eval_access)])
async def create_run(request: RunCreateRequest):
    """创建评测运行"""
    try:
        result = await runner_service.create_run(
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            num_trials=request.num_trials,
            config=request.config,
        )
        return ApiResponse(success=True, data=result, message="评测运行创建成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/start", dependencies=[Depends(verify_eval_access)])
async def start_run(run_id: str):
    """启动评测运行"""
    try:
        success = await runner_service.start_run(run_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return ApiResponse(success=True, message="评测运行已启动")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", dependencies=[Depends(verify_eval_access)])
async def list_runs(
    dataset_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
):
    """列出评测运行"""
    try:
        runs = await runner_service.list_runs(dataset_id=dataset_id, skip=skip, limit=limit)
        return ApiResponse(success=True, data={"items": runs, "count": len(runs)})
    except Exception as e:
        logger.error(f"Failed to list runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}", dependencies=[Depends(verify_eval_access)])
async def get_run(run_id: str):
    """获取评测运行详情"""
    try:
        run = await runner_service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return ApiResponse(success=True, data=run)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/cancel", dependencies=[Depends(verify_eval_access)])
async def cancel_run(run_id: str):
    """取消评测运行"""
    try:
        success = await runner_service.cancel_run(run_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found or already completed")
        return ApiResponse(success=True, message="评测运行已取消")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Trial API ====================

@router.get("/runs/{run_id}/trials", dependencies=[Depends(verify_eval_access)])
async def list_trials(
    run_id: str,
    case_id: Optional[str] = None,
):
    """列出某个运行的所有 trial"""
    try:
        trials = await runner_service.list_trials(run_id=run_id, case_id=case_id)
        return ApiResponse(success=True, data={"items": trials, "count": len(trials)})
    except Exception as e:
        logger.error(f"Failed to list trials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trials/{trial_id}", dependencies=[Depends(verify_eval_access)])
async def get_trial(trial_id: str):
    """获取 trial 详情"""
    try:
        trial = await runner_service.get_trial(trial_id)
        if not trial:
            raise HTTPException(status_code=404, detail=f"Trial {trial_id} not found")
        return ApiResponse(success=True, data=trial)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trial: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Trace API ====================

@router.get("/trials/{trial_id}/trace", dependencies=[Depends(verify_eval_access)])
async def get_trial_trace(
    trial_id: str,
    cursor: Optional[int] = None,
    limit: int = 100,
    event_types: Optional[str] = None,
):
    """获取 trial 的 trace 事件"""
    try:
        type_list = event_types.split(",") if event_types else None
        events = await trace_adapter.get_trace_events(
            trial_id=trial_id,
            cursor=cursor,
            limit=limit,
            event_types=type_list,
        )
        return ApiResponse(success=True, data={"items": events, "count": len(events)})
    except Exception as e:
        logger.error(f"Failed to get trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trials/{trial_id}/trace/summary", dependencies=[Depends(verify_eval_access)])
async def get_trace_summary(trial_id: str):
    """获取 trial 的 trace 事件摘要"""
    try:
        summary = await trace_adapter.get_events_summary(trial_id)
        return ApiResponse(success=True, data=summary)
    except Exception as e:
        logger.error(f"Failed to get trace summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 评分 API ====================

@router.get("/trials/{trial_id}/scores", dependencies=[Depends(verify_eval_access)])
async def get_trial_scores(trial_id: str):
    """获取 trial 的评分结果"""
    try:
        scores = await scorer_hub.get_trial_scores(trial_id)
        return ApiResponse(success=True, data={"items": scores, "count": len(scores)})
    except Exception as e:
        logger.error(f"Failed to get scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trials/{trial_id}/scores/summary", dependencies=[Depends(verify_eval_access)])
async def get_score_summary(trial_id: str):
    """获取 trial 的评分摘要"""
    try:
        summary = await scorer_hub.get_score_summary(trial_id)
        return ApiResponse(success=True, data=summary)
    except Exception as e:
        logger.error(f"Failed to get score summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scorers", dependencies=[Depends(verify_eval_access)])
async def list_scorers():
    """列出所有可用的评分器"""
    try:
        scorers = scorer_hub.list_scorers()
        return ApiResponse(success=True, data={"items": scorers, "count": len(scorers)})
    except Exception as e:
        logger.error(f"Failed to list scorers: {e}")
        raise HTTPException(status_code=500, detail=str(e))
