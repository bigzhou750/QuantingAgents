"""
失败聚类工具函数

从 eval router /trends 端点提取的通用失败聚类逻辑，
供 trigger_service 和自进化提案生成复用。
"""

import logging
from typing import Dict, List, Any

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)


async def cluster_failed_trials(run_ids: List[str]) -> Dict[str, Any]:
    """对指定 run 列表中的失败 trial 进行多维聚类

    Returns:
        {
            "by_error": [{"pattern": str, "count": int, "sample_trial_ids": [str]}],
            "by_scorer": [{"scorer": str, "count": int, "sample_trial_ids": [str]}],
            "by_source": [{"source": str, "count": int, "sample_trial_ids": [str]}],
            "all_failed_trial_ids": [str],
        }
    """
    db = get_mongo_db()

    failure_by_error: Dict[str, Dict] = {}
    failure_by_scorer: Dict[str, Dict] = {}
    failure_by_source: Dict[str, Dict] = {}
    all_failed_trial_ids: List[str] = []

    # 按错误消息聚类
    for run_id in run_ids:
        cursor = db["eval_trials"].find({"run_id": run_id, "status": "failed"})
        async for trial in cursor:
            trial_id = trial.get("trial_id", "")
            all_failed_trial_ids.append(trial_id)
            error_msg = trial.get("error_message", "unknown")
            cluster_key = error_msg[:80] if len(error_msg) > 80 else error_msg

            if cluster_key not in failure_by_error:
                failure_by_error[cluster_key] = {"count": 0, "sample_trial_ids": []}
            failure_by_error[cluster_key]["count"] += 1
            if len(failure_by_error[cluster_key]["sample_trial_ids"]) < 5:
                failure_by_error[cluster_key]["sample_trial_ids"].append(trial_id)

    # 按评分维度和来源聚类
    if all_failed_trial_ids:
        scores_cursor = db["eval_scores"].find({
            "trial_id": {"$in": all_failed_trial_ids},
            "score": {"$lt": 0.5},
        })
        async for score_doc in scores_cursor:
            scorer_name = score_doc.get("score_name", "unknown")
            source = score_doc.get("source", "unknown")
            trial_id = score_doc.get("trial_id", "")

            if scorer_name not in failure_by_scorer:
                failure_by_scorer[scorer_name] = {"count": 0, "sample_trial_ids": []}
            failure_by_scorer[scorer_name]["count"] += 1
            if len(failure_by_scorer[scorer_name]["sample_trial_ids"]) < 5:
                failure_by_scorer[scorer_name]["sample_trial_ids"].append(trial_id)

            if source not in failure_by_source:
                failure_by_source[source] = {"count": 0, "sample_trial_ids": []}
            failure_by_source[source]["count"] += 1
            if len(failure_by_source[source]["sample_trial_ids"]) < 5:
                failure_by_source[source]["sample_trial_ids"].append(trial_id)

    return {
        "by_error": [
            {"pattern": k, **v}
            for k, v in sorted(failure_by_error.items(), key=lambda x: -x[1]["count"])
        ],
        "by_scorer": [
            {"scorer": k, **v}
            for k, v in sorted(failure_by_scorer.items(), key=lambda x: -x[1]["count"])
        ],
        "by_source": [
            {"source": k, **v}
            for k, v in sorted(failure_by_source.items(), key=lambda x: -x[1]["count"])
        ],
        "all_failed_trial_ids": all_failed_trial_ids,
    }


def identify_primary_failure_surface(clustering_result: Dict[str, Any]) -> str:
    """根据聚类结果识别主要失败面

    Returns:
        artifact type hint: "skill" | "prompt" | "rubric" | "policy" | "case" | "unknown"
    """
    by_scorer = clustering_result.get("by_scorer", [])
    by_error = clustering_result.get("by_error", [])

    # 优先看评分维度聚类
    if by_scorer:
        top_scorer = by_scorer[0].get("scorer", "")
        scorer_to_surface = {
            "evidence_quality": "policy",      # grounding policy
            "llm_judge": "rubric",             # rubric 问题
            "trajectory": "skill",             # tool 调用/skill 问题
            "safety": "policy",                # safety policy
            "output_completeness": "prompt",   # prompt/输出格式
            "rule_based": "skill",             # 基础规则
        }
        for key, surface in scorer_to_surface.items():
            if key in top_scorer:
                return surface

    # 再看错误模式
    if by_error:
        top_pattern = by_error[0].get("pattern", "").lower()
        if "tool" in top_pattern or "skill" in top_pattern:
            return "skill"
        if "timeout" in top_pattern or "connection" in top_pattern:
            return "skill"
        if "format" in top_pattern or "parse" in top_pattern:
            return "prompt"

    return "unknown"
