"""
Agent 评测平台 API 路由

提供评测集管理、评测运行、trial 查询、trace 回放和评分复核等功能。
仅允许研发和管理员角色访问。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.routers.auth_db import get_current_user
from app.services.eval.dataset_service import dataset_service
from app.services.eval.runner_service import runner_service
from app.services.eval.trace_adapter import trace_adapter
from app.services.eval.scorer_hub import scorer_hub
from app.services.eval.metrics_service import metrics_service

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

async def verify_eval_access(current_user: dict = Depends(get_current_user)) -> dict:
    """验证评测平台访问权限

    链式依赖 get_current_user 完成 JWT 验签和用户查询后，
    再校验 is_admin 角色。返回用户对象供端点使用。
    """
    if not settings.EVAL_PLATFORM_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Agent 评测平台未启用，请联系管理员开启 EVAL_PLATFORM_ENABLED 配置"
        )

    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=403,
            detail="仅管理员可访问评测平台"
        )

    return current_user


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


class PublishVersionRequest(BaseModel):
    version: str


@router.post("/datasets/{dataset_id}/publish-version", dependencies=[Depends(verify_eval_access)])
async def publish_dataset_version(dataset_id: str, request: PublishVersionRequest):
    """手动发布语义化版本

    将数据集版本号设置为用户指定的值（如 "2.0.0"），
    用于标记一个稳定的评测基准。
    """
    try:
        result = await dataset_service.publish_version(
            dataset_id=dataset_id,
            version=request.version,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
        return ApiResponse(success=True, data=result, message=f"已发布版本 {request.version}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to publish version: {e}")
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
    version: Optional[str] = None,
):
    """列出评测集中的用例

    Args:
        version: 可选，按数据集版本过滤。不传时返回当前最新版本。
    """
    try:
        tag_list = tags.split(",") if tags else None
        cases = await dataset_service.list_cases(
            dataset_id=dataset_id,
            skip=skip,
            limit=limit,
            tags=tag_list,
            category=category,
            version=version,
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


# ==================== 人工复核 API ====================

class HumanReviewRequest(BaseModel):
    score_id: str
    new_score: float
    comment: str = ""


@router.post("/scores/human-review", dependencies=[Depends(verify_eval_access)])
async def submit_human_review(
    request: HumanReviewRequest,
    current_user: dict = Depends(verify_eval_access),
):
    """提交人工复核评分

    覆盖指定评分的分数，保留原始分数用于审计。
    """
    try:
        from app.core.database import get_mongo_db
        from app.utils.timezone import now_tz

        db = get_mongo_db()

        # 查找原始评分
        score_doc = await db["eval_scores"].find_one({"score_id": request.score_id})
        if not score_doc:
            raise HTTPException(status_code=404, detail=f"Score {request.score_id} not found")

        # 保留原始分数（如果已经被复核过，保留最初的原始分数）
        original_score = score_doc.get("original_score", score_doc.get("score"))

        # 更新评分
        await db["eval_scores"].update_one(
            {"score_id": request.score_id},
            {
                "$set": {
                    "score": max(0.0, min(1.0, request.new_score)),
                    "passed": request.new_score >= 0.6,
                    "human_reviewed": True,
                    "reviewer": current_user.get("username", "unknown"),
                    "review_comment": request.comment,
                    "original_score": original_score,
                    "updated_at": now_tz(),
                }
            }
        )

        return ApiResponse(success=True, message="人工复核已提交")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit human review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scores/pending-review", dependencies=[Depends(verify_eval_access)])
async def list_pending_reviews(
    skip: int = 0,
    limit: int = 20,
    low_confidence_threshold: float = 0.7,
):
    """列出待人工复核的评分

    返回低置信度或高风险的评分记录，供复核人处理。
    """
    try:
        from app.core.database import get_mongo_db

        db = get_mongo_db()

        query = {
            "human_reviewed": {"$ne": True},
            "$or": [
                {"confidence": {"$lt": low_confidence_threshold}},
                {"score": {"$lt": 0.5}},
            ],
        }

        cursor = db["eval_scores"].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)

        return ApiResponse(success=True, data={"items": results, "count": len(results)})
    except Exception as e:
        logger.error(f"Failed to list pending reviews: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 指标聚合 API ====================

@router.get("/runs/{run_id}/metrics", dependencies=[Depends(verify_eval_access)])
async def get_run_metrics(run_id: str, k: int = 3):
    """获取评测运行的聚合指标

    包括 pass@k、pass^k、成功率、延迟统计、token 用量等。
    """
    try:
        base_metrics = await metrics_service.compute_run_metrics(run_id)
        pass_metrics = await metrics_service.compute_pass_at_k(run_id, k=k)
        score_agg = await metrics_service.get_score_aggregation(run_id)

        combined = {**base_metrics, **pass_metrics}
        combined["score_aggregation"] = score_agg.get("scores", {})

        return ApiResponse(success=True, data=combined)
    except Exception as e:
        logger.error(f"Failed to compute run metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CompareRunsRequest(BaseModel):
    run_ids: List[str]


@router.post("/metrics/compare", dependencies=[Depends(verify_eval_access)])
async def compare_runs(request: CompareRunsRequest):
    """对比多个评测运行的指标"""
    try:
        result = await metrics_service.compare_runs(request.run_ids)
        return ApiResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"Failed to compare runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Bad Case 池 API ====================

from app.services.eval.bad_case_service import bad_case_service


class BadCaseCreateRequest(BaseModel):
    source: str  # trial_failure / human_review / safety_intercept / user_feedback
    input_data: dict
    output_data: Optional[dict] = None
    failure_reason: str = ""
    risk_level: str = "medium"
    tags: List[str] = []


class ConvertToCaseRequest(BaseModel):
    dataset_id: str


@router.get("/bad-cases", dependencies=[Depends(verify_eval_access)])
async def list_bad_cases(
    source: Optional[str] = None,
    risk_level: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
):
    """列出 Bad Case 池"""
    try:
        items = await bad_case_service.list_bad_cases(
            source=source, risk_level=risk_level, skip=skip, limit=limit
        )
        stats = await bad_case_service.get_stats()
        return ApiResponse(success=True, data={"items": items, "count": len(items), "stats": stats})
    except Exception as e:
        logger.error(f"Failed to list bad cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bad-cases", dependencies=[Depends(verify_eval_access)])
async def create_bad_case(request: BadCaseCreateRequest):
    """手动创建 Bad Case"""
    try:
        result = await bad_case_service.create_bad_case(
            source=request.source,
            input_data=request.input_data,
            output_data=request.output_data,
            failure_reason=request.failure_reason,
            risk_level=request.risk_level,
            tags=request.tags,
        )
        return ApiResponse(success=True, data=result, message="Bad Case 创建成功")
    except Exception as e:
        logger.error(f"Failed to create bad case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bad-cases/from-trial/{trial_id}", dependencies=[Depends(verify_eval_access)])
async def create_bad_case_from_trial(trial_id: str):
    """从失败的 trial 自动创建 Bad Case"""
    try:
        result = await bad_case_service.create_from_failed_trial(trial_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Trial {trial_id} not found")
        return ApiResponse(success=True, data=result, message="已从失败 trial 创建 Bad Case")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create bad case from trial: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bad-cases/{bad_case_id}/convert", dependencies=[Depends(verify_eval_access)])
async def convert_bad_case_to_dataset(bad_case_id: str, request: ConvertToCaseRequest):
    """将 Bad Case 转换为正式评测用例"""
    try:
        result = await bad_case_service.convert_to_case(
            bad_case_id=bad_case_id,
            dataset_id=request.dataset_id,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"Bad case {bad_case_id} not found")
        return ApiResponse(success=True, data=result, message="已转换为评测用例")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to convert bad case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/bad-cases/{bad_case_id}", dependencies=[Depends(verify_eval_access)])
async def delete_bad_case(bad_case_id: str):
    """删除 Bad Case"""
    try:
        success = await bad_case_service.delete_bad_case(bad_case_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Bad case {bad_case_id} not found")
        return ApiResponse(success=True, message="Bad Case 已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete bad case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 线上抽样回流 API (3.5) ====================

class OnlineSampleRequest(BaseModel):
    """线上抽样回流请求"""
    source: str = "online_sampling"  # online_sampling / user_feedback / safety_intercept
    input_data: dict
    output_data: Optional[dict] = None
    failure_reason: str = ""
    risk_level: str = "medium"
    tags: List[str] = []
    session_id: Optional[str] = None
    user_feedback: Optional[str] = None


@router.post("/online-sample", dependencies=[Depends(verify_eval_access)])
async def submit_online_sample(request: OnlineSampleRequest):
    """提交线上抽样 / 用户反馈 / 安全拦截样本到 Bad Case 池"""
    try:
        tags = list(request.tags)
        if request.session_id:
            tags.append(f"session:{request.session_id[:12]}")
        if request.user_feedback:
            tags.append("user_feedback")

        result = await bad_case_service.create_bad_case(
            source=request.source,
            input_data=request.input_data,
            output_data=request.output_data,
            failure_reason=request.failure_reason or request.user_feedback or "",
            risk_level=request.risk_level,
            tags=tags,
        )
        return ApiResponse(success=True, data=result, message="线上样本已收录")
    except Exception as e:
        logger.error(f"Failed to submit online sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 告警与报告 API (3.7) ====================

class AlertRule(BaseModel):
    """告警规则"""
    metric: str  # success_rate / cost_total / timeout_count / safety_intercept_count
    threshold: float
    direction: str = "below"  # below / above
    window_runs: int = 5  # 最近 N 次运行


@router.get("/alerts/check", dependencies=[Depends(verify_eval_access)])
async def check_alerts(dataset_id: Optional[str] = None):
    """检查告警条件

    对比最近运行的指标与预设阈值，返回触发的告警列表。
    """
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        # 默认告警规则
        rules = [
            AlertRule(metric="success_rate", threshold=0.7, direction="below"),
            AlertRule(metric="failure_rate", threshold=0.3, direction="above"),
        ]

        query = {"status": "completed"}
        if dataset_id:
            query["dataset_id"] = dataset_id

        cursor = db["eval_runs"].find(query).sort("created_at", -1).limit(5)
        recent_runs = []
        async for doc in cursor:
            recent_runs.append(doc)

        alerts = []
        if recent_runs:
            total_completed = sum(r.get("completed_trials", 0) for r in recent_runs)
            total_failed = sum(r.get("failed_trials", 0) for r in recent_runs)
            total = total_completed + total_failed

            if total > 0:
                success_rate = total_completed / total
                failure_rate = total_failed / total

                if success_rate < 0.7:
                    alerts.append({
                        "rule": "success_rate_below_0.7",
                        "current_value": round(success_rate, 4),
                        "threshold": 0.7,
                        "message": f"成功率 {success_rate:.1%} 低于 70% 阈值",
                        "severity": "warning",
                    })

                if failure_rate > 0.3:
                    alerts.append({
                        "rule": "failure_rate_above_0.3",
                        "current_value": round(failure_rate, 4),
                        "threshold": 0.3,
                        "message": f"失败率 {failure_rate:.1%} 超过 30% 阈值",
                        "severity": "critical",
                    })

        return ApiResponse(success=True, data={
            "alerts": alerts,
            "checked_runs": len(recent_runs),
            "triggered_count": len(alerts),
        })
    except Exception as e:
        logger.error(f"Failed to check alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{run_id}", dependencies=[Depends(verify_eval_access)])
async def generate_run_report(run_id: str):
    """生成评测运行报告"""
    try:
        run = await runner_service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        metrics = await metrics_service.compute_run_metrics(run_id)
        pass_metrics = await metrics_service.compute_pass_at_k(run_id)
        score_agg = await metrics_service.get_score_aggregation(run_id)

        report = {
            "run_id": run_id,
            "dataset_id": run.get("dataset_id"),
            "dataset_version": run.get("dataset_version"),
            "status": run.get("status"),
            "created_at": str(run.get("created_at", "")),
            "metrics": metrics,
            "pass_at_k": pass_metrics,
            "score_summary": score_agg.get("scores", {}),
            "generated_at": now_tz().isoformat(),
        }

        return ApiResponse(success=True, data=report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Release Gate 配置 (3.8) ====================

class ReleaseGateConfig(BaseModel):
    """发布门禁配置（预留，默认不启用）"""
    enabled: bool = False
    min_success_rate: float = 0.9
    min_pass_at_3: float = 0.8
    max_failure_rate: float = 0.1
    required_scorers: List[str] = ["rule_based", "safety"]
    block_on_safety_failure: bool = True


# 全局 release gate 配置（默认关闭）
_release_gate_config = ReleaseGateConfig()


@router.get("/release-gate/config", dependencies=[Depends(verify_eval_access)])
async def get_release_gate_config():
    """获取 release gate 配置"""
    return ApiResponse(success=True, data=_release_gate_config.model_dump())


@router.put("/release-gate/config", dependencies=[Depends(verify_eval_access)])
async def update_release_gate_config(config: ReleaseGateConfig):
    """更新 release gate 配置"""
    global _release_gate_config
    _release_gate_config = config
    return ApiResponse(success=True, data=config.model_dump(), message="Release gate 配置已更新")


@router.post("/release-gate/check/{run_id}", dependencies=[Depends(verify_eval_access)])
async def check_release_gate(run_id: str):
    """检查指定运行是否通过 release gate

    如果 release gate 未启用，直接返回 passed=true。
    """
    try:
        if not _release_gate_config.enabled:
            return ApiResponse(success=True, data={
                "passed": True,
                "enabled": False,
                "message": "Release gate 未启用",
            })

        metrics = await metrics_service.compute_run_metrics(run_id)
        pass_metrics = await metrics_service.compute_pass_at_k(run_id, k=3)

        checks = []
        failures = []

        # 成功率检查
        sr = metrics.get("success_rate", 0)
        if sr < _release_gate_config.min_success_rate:
            failures.append(f"成功率 {sr:.1%} < {_release_gate_config.min_success_rate:.1%}")
        checks.append({"metric": "success_rate", "value": sr, "passed": sr >= _release_gate_config.min_success_rate})

        # pass@3 检查
        p3 = pass_metrics.get("pass_at_k", 0)
        if p3 < _release_gate_config.min_pass_at_3:
            failures.append(f"pass@3 {p3:.1%} < {_release_gate_config.min_pass_at_3:.1%}")
        checks.append({"metric": "pass_at_3", "value": p3, "passed": p3 >= _release_gate_config.min_pass_at_3})

        # 失败率检查
        fr = metrics.get("failure_rate", 0)
        if fr > _release_gate_config.max_failure_rate:
            failures.append(f"失败率 {fr:.1%} > {_release_gate_config.max_failure_rate:.1%}")
        checks.append({"metric": "failure_rate", "value": fr, "passed": fr <= _release_gate_config.max_failure_rate})

        passed = len(failures) == 0

        return ApiResponse(success=True, data={
            "passed": passed,
            "enabled": True,
            "checks": checks,
            "failures": failures,
        })
    except Exception as e:
        logger.error(f"Failed to check release gate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 质量趋势 API (3.6) ====================

@router.get("/trends", dependencies=[Depends(verify_eval_access)])
async def get_quality_trends(
    dataset_id: Optional[str] = None,
    limit: int = 20,
):
    """获取质量趋势数据

    返回最近 N 次运行的指标趋势，用于前端图表展示。
    """
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        query = {"status": "completed"}
        if dataset_id:
            query["dataset_id"] = dataset_id

        cursor = db["eval_runs"].find(query).sort("created_at", -1).limit(limit)
        runs = []
        async for doc in cursor:
            runs.append(doc)

        # 反转使时间正序
        runs.reverse()

        trends = []
        for run in runs:
            run_id = run.get("run_id")
            metrics = await metrics_service.compute_run_metrics(run_id)
            score_agg = await metrics_service.get_score_aggregation(run_id)

            trends.append({
                "run_id": run_id,
                "dataset_id": run.get("dataset_id"),
                "dataset_version": run.get("dataset_version"),
                "created_at": str(run.get("created_at", "")),
                "success_rate": metrics.get("success_rate", 0),
                "failure_rate": metrics.get("failure_rate", 0),
                "avg_latency_ms": metrics.get("latency_stats", {}).get("mean_ms", 0),
                "total_cost_usd": metrics.get("cost_stats", {}).get("total_cost_usd", 0),
                "score_summary": {
                    name: data.get("avg", 0)
                    for name, data in score_agg.get("scores", {}).items()
                },
            })

        # 失败聚类：按错误类型分组统计
        failure_clusters = {}
        for run in runs:
            run_id = run.get("run_id")
            trials_cursor = db["eval_trials"].find({"run_id": run_id, "status": "failed"})
            async for trial in trials_cursor:
                error_msg = trial.get("error_message", "unknown")
                # 简化错误消息作为聚类 key
                cluster_key = error_msg[:80] if len(error_msg) > 80 else error_msg
                if cluster_key not in failure_clusters:
                    failure_clusters[cluster_key] = {"count": 0, "sample_run_ids": []}
                failure_clusters[cluster_key]["count"] += 1
                if len(failure_clusters[cluster_key]["sample_run_ids"]) < 3:
                    failure_clusters[cluster_key]["sample_run_ids"].append(run_id)

        return ApiResponse(success=True, data={
            "trends": trends,
            "failure_clusters": [
                {"pattern": k, **v}
                for k, v in sorted(failure_clusters.items(), key=lambda x: -x[1]["count"])
            ],
        })
    except Exception as e:
        logger.error(f"Failed to get quality trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))
