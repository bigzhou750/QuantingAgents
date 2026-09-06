"""
Agent 评测平台 API 路由

提供评测集管理、评测运行、trial 查询、trace 回放和评分复核等功能。
仅允许研发和管理员角色访问。
"""

import csv
import io
import json
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.database import get_mongo_db
from app.core.config import settings
from app.routers.auth_db import get_current_user
from app.services.eval.dataset_service import dataset_service
from app.services.eval.runner_service import runner_service
from app.services.eval.trace_adapter import trace_adapter
from app.services.eval.scorer_hub import scorer_hub
from app.services.eval.metrics_service import metrics_service
from app.models.eval import ClaimTruthLabel, HallucinationType
from app.utils.timezone import now_tz

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
    purpose: str = "general"
    metadata: dict = {}


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    purpose: Optional[str] = None
    metadata: Optional[dict] = None


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
    scorer_names: Optional[List[str]] = None
    judge_model: Optional[str] = None
    rubric_version: Optional[str] = None
    low_confidence_threshold: Optional[float] = None
    review_strategy: Optional[str] = None
    data_window: Optional[dict] = None


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
            purpose=request.purpose,
            metadata=request.metadata,
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
    purpose: Optional[str] = None,
):
    """列出评测集"""
    try:
        tag_list = tags.split(",") if tags else None
        datasets = await dataset_service.list_datasets(
            skip=skip,
            limit=limit,
            tags=tag_list,
            status=status,
            purpose=purpose,
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
            purpose=request.purpose,
            metadata=request.metadata,
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


# ==================== Golden Set 导入 & 批量操作 API ====================


@router.post("/datasets/{dataset_id}/import-golden", dependencies=[Depends(verify_eval_access)])
async def import_golden_cases(dataset_id: str):
    """将内置 Golden Set 用例导入到指定评测集（幂等）"""
    try:
        result = await dataset_service.import_golden_cases(dataset_id=dataset_id)
        return ApiResponse(
            success=True,
            data=result,
            message=f"Golden cases 导入完成：{result['imported']} 条新增，{result['skipped']} 条跳过",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to import golden cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BatchImportCasesRequest(BaseModel):
    cases: List[CaseCreateRequest]


def parse_case_import_file(content: bytes, filename: str) -> List[dict]:
    """把 JSON/CSV/Excel 导入文件解析成 Case 行字典。"""
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "json":
        try:
            rows = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"JSON 文件无法解析: {exc}")
        if not isinstance(rows, list):
            raise ValueError("JSON 文件必须是 case 数组")
        return rows

    if ext == "csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"CSV 文件编码不支持: {exc}")
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    if ext in ("xlsx", "xls"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError("Excel 导入需要安装 openpyxl") from exc
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            header_cells = next(ws.iter_rows())
            headers = [str(c.value).strip() if c.value is not None else "" for c in header_cells]
            rows = []
            for row in ws.iter_rows(min_row=2):
                values = [c.value for c in row]
                if any(v is not None and str(v).strip() for v in values):
                    rows.append(dict(zip(headers, values)))
            wb.close()
            return rows
        except Exception as exc:
            raise ValueError(f"Excel 文件无法解析: {exc}") from exc

    raise ValueError("仅支持 .json、.csv、.xlsx 导入文件")


@router.post("/datasets/{dataset_id}/cases/batch-import", dependencies=[Depends(verify_eval_access)])
async def batch_import_cases(dataset_id: str, request: BatchImportCasesRequest):
    """批量导入用例到评测集"""
    imported = 0
    failed = 0
    errors = []

    for idx, case in enumerate(request.cases):
        try:
            await dataset_service.add_case(
                dataset_id=dataset_id,
                name=case.name,
                input_data=case.input,
                expected_output=case.expected_output,
                scoring_criteria=case.scoring_criteria,
                tags=case.tags,
                difficulty=case.difficulty,
                category=case.category,
                description=case.description,
            )
            imported += 1
        except Exception as e:
            failed += 1
            errors.append({
                "index": idx,
                "name": case.name,
                "error": str(e),
            })

    return ApiResponse(
        success=True,
        data={"imported": imported, "failed": failed, "errors": errors},
        message=f"批量导入完成：{imported} 条成功，{failed} 条失败",
    )


@router.post("/datasets/{dataset_id}/cases/upload", dependencies=[Depends(verify_eval_access)])
async def upload_cases_file(
    dataset_id: str,
    file: UploadFile = File(...),
):
    """从 JSON/CSV/Excel 文件批量导入用例，逐行报告部分失败。"""
    content = await file.read()
    try:
        rows = parse_case_import_file(content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    imported = 0
    failed = 0
    errors = []
    for idx, row in enumerate(rows):
        try:
            name = str(row.get("name", "")).strip()
            if not name:
                raise ValueError("缺少 name 字段")
            input_data = row.get("input")
            if isinstance(input_data, str):
                input_data = json.loads(input_data)
            if not isinstance(input_data, dict):
                raise ValueError("input 必须是对象或合法 JSON 字符串")

            expected_output = row.get("expected_output")
            if isinstance(expected_output, str) and expected_output.strip():
                expected_output = json.loads(expected_output)
            scoring_criteria = row.get("scoring_criteria")
            if isinstance(scoring_criteria, str) and scoring_criteria.strip():
                scoring_criteria = json.loads(scoring_criteria)

            tags = row.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            await dataset_service.add_case(
                dataset_id=dataset_id,
                name=name,
                input_data=input_data,
                expected_output=expected_output,
                scoring_criteria=scoring_criteria,
                tags=tags,
                difficulty=str(row.get("difficulty") or "medium"),
                category=str(row.get("category") or "general"),
                description=str(row.get("description") or ""),
            )
            imported += 1
        except Exception as exc:
            failed += 1
            errors.append({
                "index": idx,
                "name": row.get("name", ""),
                "error": str(exc),
            })

    return ApiResponse(
        success=True,
        data={"imported": imported, "failed": failed, "errors": errors},
        message=f"文件导入完成：{imported} 条成功，{failed} 条失败",
    )


class BatchUpdateCasesRequest(BaseModel):
    case_ids: List[str]
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    scoring_criteria: Optional[dict] = None


@router.put("/datasets/{dataset_id}/cases/batch-update", dependencies=[Depends(verify_eval_access)])
async def batch_update_cases(dataset_id: str, request: BatchUpdateCasesRequest):
    """批量更新评测用例的公共字段"""
    try:
        result = await dataset_service.batch_update_cases(
            case_ids=request.case_ids,
            tags=request.tags,
            category=request.category,
            difficulty=request.difficulty,
            scoring_criteria=request.scoring_criteria,
        )
        return ApiResponse(
            success=True,
            data=result,
            message=f"批量更新完成：{result['updated']} 条用例已更新",
        )
    except Exception as e:
        logger.error(f"Failed to batch update cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 评测运行 API ====================

@router.post("/runs", dependencies=[Depends(verify_eval_access)])
async def create_run(request: RunCreateRequest):
    """创建评测运行"""
    try:
        # 合并显式配置字段到 config dict
        config = dict(request.config)
        if request.scorer_names is not None:
            config["scorer_names"] = request.scorer_names
        if request.judge_model is not None:
            config["judge_model"] = request.judge_model
        if request.rubric_version is not None:
            config["rubric_version"] = request.rubric_version
        if request.low_confidence_threshold is not None:
            config["low_confidence_threshold"] = request.low_confidence_threshold
        if request.review_strategy is not None:
            config["review_strategy"] = request.review_strategy
        if request.data_window is not None:
            config["data_window"] = request.data_window

        result = await runner_service.create_run(
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            num_trials=request.num_trials,
            config=config,
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
    action: str = "adjust_score"  # approve / reject / adjust_score / add_bad_case / reflow
    target_dataset_id: Optional[str] = None  # for reflow action


class ClaimAnnotationRequest(BaseModel):
    score_id: str = Field(..., min_length=1)
    claim_id: str = Field(..., min_length=1)
    truth_label: ClaimTruthLabel
    hallucination_type: Optional[HallucinationType] = None
    label_version: str = Field(..., min_length=1)
    comment: str = ""


@router.post("/scores/claims/annotation", dependencies=[Depends(verify_eval_access)])
async def annotate_claim(
    request: ClaimAnnotationRequest,
    current_user: dict = Depends(verify_eval_access),
):
    """保存 Claim 级人工真值，供幻觉分类指标使用。"""
    try:
        from app.core.database import get_mongo_db

        db = get_mongo_db()
        score_doc = await db["eval_scores"].find_one({
            "score_id": request.score_id,
            "claims.claim_id": request.claim_id,
        })
        if not score_doc:
            raise HTTPException(status_code=404, detail="Score 或 Claim 不存在")

        now = now_tz()
        update = {
            "claims.$.truth_label": request.truth_label.value,
            "claims.$.truth_source": request.comment or current_user.get("username", "unknown"),
            "claims.$.hallucination_type": (
                request.hallucination_type.value if request.hallucination_type else None
            ),
            "claims.$.label_version": request.label_version,
            "updated_at": now,
        }
        await db["eval_scores"].update_one(
            {"score_id": request.score_id, "claims.claim_id": request.claim_id},
            {"$set": update},
        )
        return ApiResponse(
            success=True,
            data={
                "score_id": request.score_id,
                "claim_id": request.claim_id,
                "truth_label": request.truth_label.value,
                "label_version": request.label_version,
            },
            message="Claim 标注已保存",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to annotate claim: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        db = get_mongo_db()

        # 查找原始评分
        score_doc = await db["eval_scores"].find_one({"score_id": request.score_id})
        if not score_doc:
            raise HTTPException(status_code=404, detail=f"Score {request.score_id} not found")

        # 保留原始分数（如果已经被复核过，保留最初的原始分数）
        original_score = score_doc.get("original_score", score_doc.get("score"))

        clamped_score = max(0.0, min(1.0, request.new_score))
        new_status = "passed" if clamped_score >= 0.6 else "failed"

        # 更新评分
        await db["eval_scores"].update_one(
            {"score_id": request.score_id},
            {
                "$set": {
                    "score": clamped_score,
                    "passed": clamped_score >= 0.6,
                    "status": new_status,
                    "review_action": request.action,
                    "human_reviewed": True,
                    "reviewer": current_user.get("username", "unknown"),
                    "review_comment": request.comment,
                    "original_score": original_score,
                    "updated_at": now_tz(),
                },
                "$push": {
                    "review_audit_trail": {
                        "reviewer": current_user.get("username", "unknown"),
                        "action": request.action,
                        "old_score": original_score,
                        "new_score": clamped_score,
                        "comment": request.comment,
                        "timestamp": now_tz(),
                    }
                },
            }
        )

        # add_bad_case action: create a bad case from the trial
        if request.action == "add_bad_case":
            trial_id = score_doc.get("trial_id")
            if trial_id:
                try:
                    await bad_case_service.create_from_failed_trial(trial_id)
                except Exception as e:
                    logger.warning(f"Failed to create bad case from trial {trial_id}: {e}")

        # reflow action: convert bad case to dataset case
        if request.action == "reflow" and request.target_dataset_id:
            trial_id = score_doc.get("trial_id")
            if trial_id:
                try:
                    # Find existing bad case for this trial, or create one first
                    # Bad cases store the reference as source_trial_id
                    bad_case_doc = await db["eval_bad_cases"].find_one({"source_trial_id": trial_id})
                    if bad_case_doc:
                        bc_id = bad_case_doc.get("bad_case_id", str(bad_case_doc.get("_id", "")))
                    else:
                        created = await bad_case_service.create_from_failed_trial(trial_id)
                        bc_id = created.get("bad_case_id") if created else None
                    if bc_id:
                        await bad_case_service.convert_to_case(
                            bad_case_id=str(bc_id),
                            dataset_id=request.target_dataset_id,
                        )
                except Exception as e:
                    logger.warning(f"Failed to reflow bad case for trial {trial_id}: {e}")

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
    run_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    source: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
):
    """列出待人工复核的评分

    返回低置信度或高风险的评分记录，供复核人处理。
    支持按 run_id、dataset_id、source 和置信度范围过滤。
    """
    try:
        from app.core.database import get_mongo_db

        db = get_mongo_db()

        query = {
            "human_reviewed": {"$ne": True},
            # 排除非真实评分状态，避免未启用/出错的评分器进入待复核队列
            "status": {"$nin": ["skipped", "not_configured", "error"]},
            "$or": [
                {"confidence": {"$lt": low_confidence_threshold}},
                {"score": {"$lt": 0.5}},
            ],
        }

        # Filter by source (scorer name)
        if source is not None:
            query["scorer_name"] = source

        # Filter by confidence range
        if min_confidence is not None or max_confidence is not None:
            confidence_filter = {}
            if min_confidence is not None:
                confidence_filter["$gte"] = min_confidence
            if max_confidence is not None:
                confidence_filter["$lte"] = max_confidence
            query["confidence"] = confidence_filter

        # Filter by run_id or dataset_id via trial subquery
        if run_id is not None or dataset_id is not None:
            trial_query = {}
            if run_id is not None:
                trial_query["run_id"] = run_id
            if dataset_id is not None:
                trial_query["dataset_id"] = dataset_id

            matching_trial_ids = []
            trial_cursor = db["eval_trials"].find(trial_query, {"trial_id": 1})
            async for t in trial_cursor:
                tid = t.get("trial_id")
                if tid:
                    matching_trial_ids.append(tid)

            query["trial_id"] = {"$in": matching_trial_ids}

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
        claim_summary = await metrics_service.get_claim_summary(run_id)

        combined = {**base_metrics, **pass_metrics}
        combined["score_aggregation"] = score_agg.get("scores", {})
        combined["claim_summary"] = claim_summary

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
    failure_family: Optional[str] = None


class ConvertToCaseRequest(BaseModel):
    dataset_id: str


class BadCaseReviewRequest(BaseModel):
    action: str
    comment: str = ""
    failure_family: Optional[str] = None
    tags: Optional[List[str]] = None
    label_version: Optional[str] = None


@router.get("/bad-cases", dependencies=[Depends(verify_eval_access)])
async def list_bad_cases(
    source: Optional[str] = None,
    risk_level: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    detection_status: Optional[str] = None,
    review_status: Optional[str] = None,
    failure_family: Optional[str] = None,
):
    """列出 Bad Case 池"""
    try:
        items = await bad_case_service.list_bad_cases(
            source=source,
            risk_level=risk_level,
            skip=skip,
            limit=limit,
            detection_status=detection_status,
            review_status=review_status,
            failure_family=failure_family,
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
            failure_family=request.failure_family,
        )
        return ApiResponse(success=True, data=result, message="Bad Case 创建成功")
    except Exception as e:
        logger.error(f"Failed to create bad case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bad-cases/review-queue", dependencies=[Depends(verify_eval_access)])
async def list_bad_case_review_queue(skip: int = 0, limit: int = 50):
    """获取待复核 Bad Case"""
    try:
        items = await bad_case_service.list_review_queue(skip=skip, limit=limit)
        return ApiResponse(success=True, data={"items": items, "count": len(items)})
    except Exception as e:
        logger.error(f"Failed to list bad case review queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bad-cases/{bad_case_id}", dependencies=[Depends(verify_eval_access)])
async def get_bad_case(bad_case_id: str):
    """获取 Bad Case 详情"""
    try:
        result = await bad_case_service.get_bad_case(bad_case_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Bad case {bad_case_id} not found")
        return ApiResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get bad case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bad-cases/{bad_case_id}/review", dependencies=[Depends(verify_eval_access)])
async def review_bad_case(
    bad_case_id: str,
    request: BadCaseReviewRequest,
    user: dict = Depends(verify_eval_access),
):
    """复核 Bad Case"""
    try:
        result = await bad_case_service.review_bad_case(
            bad_case_id=bad_case_id,
            action=request.action,
            reviewer=user.get("username", "unknown"),
            comment=request.comment,
            failure_family=request.failure_family,
            tags=request.tags,
            label_version=request.label_version,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"Bad case {bad_case_id} not found")
        return ApiResponse(success=True, data=result, message="Bad Case 复核完成")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to review bad case: {e}")
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
    source_trace_id: Optional[str] = None
    release_receipt_id: Optional[str] = None
    artifact_version: Optional[str] = None


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
            source_trial_id=request.source_trace_id,
            source_run_id=request.release_receipt_id,
            source_trace_id=request.source_trace_id,
            release_receipt_id=request.release_receipt_id,
            artifact_version=request.artifact_version,
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
            pass_metrics = await metrics_service.compute_pass_at_k(run_id)

            latency = metrics.get("latency", {}) or {}
            cost = metrics.get("cost", {}) or {}

            trends.append({
                "run_id": run_id,
                "dataset_id": run.get("dataset_id"),
                "dataset_version": run.get("dataset_version"),
                "created_at": str(run.get("created_at", "")),
                "success_rate": metrics.get("success_rate", 0),
                "failure_rate": metrics.get("failure_rate", 0),
                "avg_latency_ms": latency.get("mean_ms", 0),
                "total_cost_usd": cost.get("total_usd", 0),
                "pass_at_k": pass_metrics.get("pass_at_k", 0),
                "pass_pow_k": pass_metrics.get("pass_pow_k", 0),
                "pass_k": pass_metrics.get("k", 3),
                "score_summary": {
                    name: data.get("avg_score", 0)
                    for name, data in score_agg.get("scores", {}).items()
                },
            })

        # 失败聚类 (6.2)：按错误类型、评分维度、数据源多维聚类
        failure_clusters_by_error = {}
        failure_clusters_by_scorer = {}
        failure_clusters_by_source = {}

        all_failed_trial_ids = []
        for run in runs:
            run_id = run.get("run_id")
            trials_cursor = db["eval_trials"].find({"run_id": run_id, "status": "failed"})
            async for trial in trials_cursor:
                trial_id = trial.get("trial_id")
                all_failed_trial_ids.append(trial_id)
                error_msg = trial.get("error_message", "unknown")
                cluster_key = error_msg[:80] if len(error_msg) > 80 else error_msg
                if cluster_key not in failure_clusters_by_error:
                    failure_clusters_by_error[cluster_key] = {"count": 0, "sample_run_ids": [], "sample_trial_ids": []}
                failure_clusters_by_error[cluster_key]["count"] += 1
                if len(failure_clusters_by_error[cluster_key]["sample_run_ids"]) < 3:
                    failure_clusters_by_error[cluster_key]["sample_run_ids"].append(run_id)
                    failure_clusters_by_error[cluster_key]["sample_trial_ids"].append(trial_id)

        # 按评分维度聚类：查找 failed trial 中 score < 0.5 的评分器
        if all_failed_trial_ids:
            scores_cursor = db["eval_scores"].find({
                "trial_id": {"$in": all_failed_trial_ids},
                "score": {"$lt": 0.5},
            })
            async for score_doc in scores_cursor:
                scorer_name = score_doc.get("score_name", "unknown")
                source = score_doc.get("source", "unknown")
                trial_id = score_doc.get("trial_id", "")

                # 按评分器聚类
                if scorer_name not in failure_clusters_by_scorer:
                    failure_clusters_by_scorer[scorer_name] = {"count": 0, "sample_trial_ids": []}
                failure_clusters_by_scorer[scorer_name]["count"] += 1
                if len(failure_clusters_by_scorer[scorer_name]["sample_trial_ids"]) < 3:
                    failure_clusters_by_scorer[scorer_name]["sample_trial_ids"].append(trial_id)

                # 按来源聚类
                if source not in failure_clusters_by_source:
                    failure_clusters_by_source[source] = {"count": 0, "sample_trial_ids": []}
                failure_clusters_by_source[source]["count"] += 1
                if len(failure_clusters_by_source[source]["sample_trial_ids"]) < 3:
                    failure_clusters_by_source[source]["sample_trial_ids"].append(trial_id)

        return ApiResponse(success=True, data={
            "trends": trends,
            "failure_clusters": [
                {"pattern": k, **v}
                for k, v in sorted(failure_clusters_by_error.items(), key=lambda x: -x[1]["count"])
            ],
            "failure_by_scorer": [
                {"scorer": k, **v}
                for k, v in sorted(failure_clusters_by_scorer.items(), key=lambda x: -x[1]["count"])
            ],
            "failure_by_source": [
                {"source": k, **v}
                for k, v in sorted(failure_clusters_by_source.items(), key=lambda x: -x[1]["count"])
            ],
        })
    except Exception as e:
        logger.error(f"Failed to get quality trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 定时回归任务 (6.4) ====================

class RegressionTaskConfig(BaseModel):
    """定时回归任务配置"""
    task_id: str = ""
    name: str = ""
    dataset_id: str = ""
    agent_name: str = ""
    num_trials_per_case: int = 1
    scorer_names: List[str] = []
    schedule_cron: str = ""  # cron 表达式，空表示不自动执行
    enabled: bool = False
    created_at: Optional[str] = None
    last_run_id: Optional[str] = None
    last_run_at: Optional[str] = None


class EvalGovernanceConfig(BaseModel):
    """评测成本告警和第三方观测配置。"""
    daily_cost_budget_usd: float = 0.0
    alert_enabled: bool = True
    alert_webhook: str = ""
    observability_backend: str = "none"
    observability_api_key: str = ""
    observability_host: str = ""
    observability_project: str = "quantingagents-eval"


@router.get("/governance/config", dependencies=[Depends(verify_eval_access)])
async def get_governance_config():
    """读取评测成本、告警和观测配置。"""
    try:
        db = get_mongo_db()
        doc = await db["eval_governance_config"].find_one({"config_id": "default"})
        if doc:
            doc.pop("_id", None)
            return ApiResponse(success=True, data=doc)
        return ApiResponse(success=True, data=EvalGovernanceConfig().model_dump())
    except Exception as e:
        logger.error(f"Failed to get governance config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/governance/config", dependencies=[Depends(verify_eval_access)])
async def update_governance_config(config: EvalGovernanceConfig):
    """保存评测成本、告警和观测配置，并应用观测适配器设置。"""
    try:
        if config.observability_backend not in {"none", "langfuse", "phoenix"}:
            raise HTTPException(status_code=400, detail="不支持的观测后端")
        db = get_mongo_db()
        doc = config.model_dump()
        doc["config_id"] = "default"
        doc["updated_at"] = now_tz()
        await db["eval_governance_config"].update_one(
            {"config_id": "default"}, {"$set": doc}, upsert=True
        )
        from app.services.eval.observability_adapter import observability_adapter
        observability_adapter.configure(
            backend=config.observability_backend,
            api_key=config.observability_api_key,
            host=config.observability_host,
            project=config.observability_project,
        )
        response = config.model_dump()
        response["updated_at"] = doc["updated_at"].isoformat()
        return ApiResponse(success=True, data=response, message="评测治理配置已保存")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update governance config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regression-tasks", dependencies=[Depends(verify_eval_access)])
async def list_regression_tasks():
    """列出所有回归任务配置"""
    try:
        db = get_mongo_db()
        cursor = db["eval_regression_tasks"].find().sort("created_at", -1)
        items = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            items.append(doc)
        return ApiResponse(success=True, data={"items": items})
    except Exception as e:
        logger.error(f"Failed to list regression tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regression-tasks", dependencies=[Depends(verify_eval_access)])
async def create_regression_task(config: RegressionTaskConfig):
    """创建回归任务配置（默认禁用）"""
    import uuid
    try:
        db = get_mongo_db()
        task_id = config.task_id or f"reg_{uuid.uuid4().hex[:8]}"
        doc = config.model_dump()
        doc["task_id"] = task_id
        doc["enabled"] = False  # 默认禁用，需手动启用
        doc["created_at"] = now_tz().isoformat()

        await db["eval_regression_tasks"].update_one(
            {"task_id": task_id},
            {"$set": doc},
            upsert=True,
        )
        return ApiResponse(success=True, data=doc, message="回归任务已创建（默认禁用）")
    except Exception as e:
        logger.error(f"Failed to create regression task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/regression-tasks/{task_id}/toggle", dependencies=[Depends(verify_eval_access)])
async def toggle_regression_task(task_id: str, enabled: bool = True):
    """启用/禁用回归任务"""
    try:
        db = get_mongo_db()
        result = await db["eval_regression_tasks"].update_one(
            {"task_id": task_id},
            {"$set": {"enabled": enabled}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        return ApiResponse(success=True, message=f"任务已{'启用' if enabled else '禁用'}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle regression task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regression-tasks/{task_id}/trigger", dependencies=[Depends(verify_eval_access)])
async def trigger_regression_task(task_id: str):
    """手动触发一次回归运行"""
    try:
        db = get_mongo_db()
        task_doc = await db["eval_regression_tasks"].find_one({"task_id": task_id})
        if not task_doc:
            raise HTTPException(status_code=404, detail="Task not found")

        # 创建评测运行
        run_config = {
            "dataset_id": task_doc.get("dataset_id"),
            "agent_name": task_doc.get("agent_name", ""),
            "num_trials_per_case": task_doc.get("num_trials_per_case", 1),
            "scorer_names": task_doc.get("scorer_names", []),
        }

        from app.services.eval.runner_service import runner_service
        run = await runner_service.create_run(
            dataset_id=run_config["dataset_id"],
            num_trials=run_config.get("num_trials_per_case", 1),
            config={
                "agent_name": run_config.get("agent_name", ""),
                "scorer_names": run_config.get("scorer_names", []),
            },
            created_by="regression_task",
        )
        run_id = run.get("run_id", "")

        # 启动运行
        await runner_service.start_run(run_id)

        # 更新最后运行信息
        await db["eval_regression_tasks"].update_one(
            {"task_id": task_id},
            {"$set": {"last_run_id": run_id, "last_run_at": now_tz().isoformat()}},
        )

        return ApiResponse(success=True, data={"run_id": run_id}, message="回归运行已触发")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger regression task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注：POST /bad-cases/from-trial/{trial_id} 已在上方 L906 定义（create_bad_case_from_trial）
# POST /online-sample 已在上方 L968 定义
