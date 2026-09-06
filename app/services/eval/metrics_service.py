"""
评测指标聚合服务

计算跨 trial/run 的聚合指标：
- pass@k: k 次 trial 中至少通过一次的概率
- pass^k: k 次 trial 全部通过的概率
- 方差 / 标准差
- 成功率 / 失败率
- 平均成本 / 延迟 / token 用量
- 跨版本对比

对应 spec 二期任务 2.8。
"""

import math
import logging
from typing import Optional, List, Dict, Any
from collections import defaultdict

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)


def _annotation_consensus(claim: Dict[str, Any]) -> tuple[Optional[str], str]:
    """从 annotation_history 解析多人标注一致性。"""
    history = claim.get("annotation_history") or []
    labels = [
        annotation.get("truth_label")
        for annotation in history
        if annotation.get("truth_label")
    ]
    if not labels:
        return None, "single"
    normalized = {str(label).lower() for label in labels}
    if len(normalized) == 1:
        return str(labels[-1]).lower(), "agreed"
    return None, "disputed"


class MetricsService:
    """评测指标聚合服务"""

    @staticmethod
    def compute_hallucination_metrics(
        claims: List[Dict[str, Any]],
        *,
        weakly_supported: str = "exclude",
    ) -> Dict[str, Any]:
        """计算 Claim 级幻觉分类指标。

        truth_label 是人工真值；prediction_label 是评分器预测。
        weakly_supported 仅影响缺失 truth_label 的旧 verdict 映射，默认排除。
        """
        confusion = {key: 0 for key in ("tp", "fp", "fn", "tn")}
        by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        eligible = 0
        excluded = 0

        normalized_claims: List[Dict[str, Any]] = []
        annotation_consistency_counts = {"single": 0, "agreed": 0, "disputed": 0}
        for original_claim in claims:
            claim = dict(original_claim)
            consensus_label, consistency = _annotation_consensus(claim)
            claim["annotation_consistency"] = consistency
            annotation_consistency_counts[consistency] = annotation_consistency_counts.get(consistency, 0) + 1
            if consistency == "disputed":
                excluded += 1
                continue
            if consensus_label is not None and claim.get("truth_label") is None:
                claim["truth_label"] = consensus_label
            truth = claim.get("truth_label")
            prediction = claim.get("prediction_label")
            if truth is None and claim.get("verdict") == "weakly_supported":
                if weakly_supported == "unsupported":
                    truth = "unsupported"
                elif weakly_supported == "supported":
                    truth = "supported"
            if (
                truth is None
                or prediction is None
                or not claim.get("truth_source")
                or not claim.get("label_version")
            ):
                excluded += 1
                continue
            if isinstance(truth, dict):
                truth = truth.get("value") or truth.get("name")
            if truth == "excluded":
                excluded += 1
                continue
            if truth not in ("supported", "unsupported", "contradicted"):
                excluded += 1
                continue
            claim["truth_label"] = truth
            normalized_claims.append(claim)

            truth_hallucinated = truth in ("unsupported", "contradicted")
            predicted_hallucinated = bool(prediction)
            if truth_hallucinated and predicted_hallucinated:
                confusion["tp"] += 1
            elif not truth_hallucinated and predicted_hallucinated:
                confusion["fp"] += 1
            elif truth_hallucinated:
                confusion["fn"] += 1
            else:
                confusion["tn"] += 1
            eligible += 1
            claim_type = claim.get("hallucination_type") or "all"
            if isinstance(claim_type, dict):
                claim_type = claim_type.get("value") or claim_type.get("name") or "other"
            by_type[str(claim_type)].append(claim)

        def calculate(items: List[Dict[str, Any]]) -> Dict[str, Any]:
            matrix = {key: 0 for key in ("tp", "fp", "fn", "tn")}
            for item in items:
                truth = item.get("truth_label")
                prediction = bool(item.get("prediction_label"))
                if isinstance(truth, dict):
                    truth = truth.get("value") or truth.get("name")
                if truth in ("unsupported", "contradicted") and prediction:
                    matrix["tp"] += 1
                elif truth == "supported" and prediction:
                    matrix["fp"] += 1
                elif truth in ("unsupported", "contradicted"):
                    matrix["fn"] += 1
                elif truth == "supported":
                    matrix["tn"] += 1
            precision_denominator = matrix["tp"] + matrix["fp"]
            recall_denominator = matrix["tp"] + matrix["fn"]
            precision = matrix["tp"] / precision_denominator if precision_denominator else None
            recall = matrix["tp"] / recall_denominator if recall_denominator else None
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision is not None and recall is not None and precision + recall
                else None
            )
            return {
                **matrix,
                "samples": sum(matrix.values()),
                "precision": round(precision, 4) if precision is not None else None,
                "recall": round(recall, 4) if recall is not None else None,
                "f1": round(f1, 4) if f1 is not None else None,
                "status": "available" if sum(matrix.values()) else "not_available",
            }

        result = calculate(normalized_claims)
        unsupported_claims = [c for c in normalized_claims if c["truth_label"] == "unsupported"]
        contradicted_claims = [c for c in normalized_claims if c["truth_label"] == "contradicted"]
        unsupported_fn = sum(1 for c in unsupported_claims if not c.get("prediction_label"))
        contradicted_fn = sum(1 for c in contradicted_claims if not c.get("prediction_label"))
        result.update({
            "eligible_claims": eligible,
            "excluded_claims": excluded,
            "annotation_consistency": annotation_consistency_counts,
            "weakly_supported_policy": weakly_supported,
            "metric_definition": {
                "positive_class": ["unsupported", "contradicted"],
                "unsupported_pass_rate": "unsupported FN / unsupported total",
                "contradicted_pass_rate": "contradicted FN / contradicted total",
            },
            "unsupported_pass_rate": round(unsupported_fn / len(unsupported_claims), 4) if unsupported_claims else None,
            "contradicted_pass_rate": round(contradicted_fn / len(contradicted_claims), 4) if contradicted_claims else None,
            "by_type": {key: calculate(value) for key, value in by_type.items() if key != "all"},
        })
        return result

    async def compute_run_metrics(self, run_id: str) -> Dict[str, Any]:
        """计算单个 run 的聚合指标"""
        db = get_mongo_db()

        # 获取所有 trial
        cursor = db["eval_trials"].find({"run_id": run_id})
        trials = []
        async for doc in cursor:
            trials.append(doc)

        if not trials:
            return {"run_id": run_id, "total_trials": 0}

        total = len(trials)
        completed = [t for t in trials if t.get("status") == "completed"]
        failed = [t for t in trials if t.get("status") in ("failed", "timeout")]
        cancelled = [t for t in trials if t.get("status") == "cancelled"]

        # 基础统计
        latencies = [t.get("latency_ms", 0) for t in completed if t.get("latency_ms")]
        token_usages = []
        costs = []
        for t in completed:
            tu = t.get("token_usage", {})
            if isinstance(tu, dict) and tu:
                token_usages.append(sum(tu.values()))
            cost = t.get("cost_usd", 0)
            if cost:
                costs.append(cost)

        result = {
            "run_id": run_id,
            "total_trials": total,
            "completed_count": len(completed),
            "failed_count": len(failed),
            "cancelled_count": len(cancelled),
            "success_rate": round(len(completed) / max(1, total), 4),
            "failure_rate": round(len(failed) / max(1, total), 4),
        }

        # 延迟统计
        if latencies:
            result["latency"] = {
                "mean_ms": round(sum(latencies) / len(latencies), 1),
                "p50_ms": round(sorted(latencies)[len(latencies) // 2], 1),
                "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
                "stddev_ms": round(self._stddev(latencies), 1),
            }

        # Token 统计
        if token_usages:
            result["tokens"] = {
                "mean": round(sum(token_usages) / len(token_usages), 1),
                "total": sum(token_usages),
            }

        # 成本统计
        if costs:
            result["cost"] = {
                "mean_usd": round(sum(costs) / len(costs), 6),
                "total_usd": round(sum(costs), 6),
            }

        return result

    async def compute_pass_at_k(
        self,
        run_id: str,
        k: int = 3,
        mode: str = "quality",
    ) -> Dict[str, Any]:
        """计算 pass@k 和 pass^k

        mode=quality 时按有效评分是否通过计算；mode=execution 时按 trial
        是否正常完成计算。两种口径必须在响应中显式区分。
        """
        db = get_mongo_db()

        if mode not in {"quality", "execution"}:
            raise ValueError("mode must be quality or execution")

        # 按 case_id 分组
        cursor = db["eval_trials"].find({"run_id": run_id})
        case_trials: Dict[str, List[Dict]] = defaultdict(list)
        async for doc in cursor:
            case_trials[doc.get("case_id", "")].append(doc)

        if not case_trials:
            return {"pass_at_k": 0.0, "pass_pow_k": 0.0, "k": k, "cases": 0, "mode": mode}

        scores_by_trial: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        if mode == "quality":
            trial_ids = [t.get("trial_id") for trials in case_trials.values() for t in trials if t.get("trial_id")]
            score_cursor = db["eval_scores"].find({"trial_id": {"$in": trial_ids}})
            async for score in score_cursor:
                scores_by_trial[score.get("trial_id", "")].append(score)

            run_doc = await db["eval_runs"].find_one({"run_id": run_id}, {"config": 1})
            run_config = (run_doc or {}).get("config") or {}
            required_scorers = run_config.get("required_scorers") or run_config.get("scorer_names") or []
            quality_threshold = float(run_config.get("quality_pass_threshold", 0.6))

        def trial_passed(trial: Dict[str, Any]) -> bool:
            if mode == "execution":
                return trial.get("status") == "completed"
            if trial.get("status") != "completed":
                return False
            scores = [
                score for score in scores_by_trial.get(trial.get("trial_id", ""), [])
                if score.get("status") in {"passed", "failed"}
            ]
            if required_scorers:
                scores = [score for score in scores if score.get("score_name") in required_scorers]
                if {score.get("score_name") for score in scores} != set(required_scorers):
                    return False
            if not scores:
                return False
            return all(
                score.get("passed") is True and float(score.get("score", 0.0)) >= quality_threshold
                for score in scores
            )

        pass_at_k_values = []
        pass_pow_k_values = []
        per_case = {}

        for case_id, trials in case_trials.items():
            n = len(trials)
            passed = sum(1 for t in trials if trial_passed(t))
            failed = n - passed

            if n < k:
                # trial 数不足 k，用实际数量计算
                actual_k = n
            else:
                actual_k = k

            # pass@k = 1 - C(failed, k) / C(n, k)
            if failed >= actual_k:
                # 从组合数学角度，如果失败数 >= k，则有可能 k 次都失败
                pass_at_k = 1.0 - self._combination(failed, actual_k) / max(1, self._combination(n, actual_k))
            else:
                pass_at_k = 1.0  # 失败数 < k，必然至少有一次通过

            # pass^k = C(passed, k) / C(n, k)
            if passed >= actual_k:
                pass_pow_k = self._combination(passed, actual_k) / max(1, self._combination(n, actual_k))
            else:
                pass_pow_k = 0.0

            pass_at_k_values.append(max(0.0, min(1.0, pass_at_k)))
            pass_pow_k_values.append(max(0.0, min(1.0, pass_pow_k)))
            per_case[case_id] = {
                "pass_at_k": round(pass_at_k, 4),
                "pass_pow_k": round(pass_pow_k, 4),
                "trials": n,
                "passed_trials": passed,
                "failed_trials": failed,
            }

        return {
            "pass_at_k": round(sum(pass_at_k_values) / len(pass_at_k_values), 4) if pass_at_k_values else 0.0,
            "pass_pow_k": round(sum(pass_pow_k_values) / len(pass_pow_k_values), 4) if pass_pow_k_values else 0.0,
            "k": k,
            "cases": len(case_trials),
            "mode": mode,
            "per_case": per_case,
        }

    async def compare_runs(
        self,
        run_ids: List[str],
    ) -> Dict[str, Any]:
        """对比多个 run 的指标"""
        comparisons = []
        for run_id in run_ids:
            metrics = await self.compute_run_metrics(run_id)
            run_doc = await get_mongo_db()["eval_runs"].find_one({"run_id": run_id})
            if run_doc:
                metrics["dataset_version"] = run_doc.get("dataset_version", "")
                metrics["created_at"] = str(run_doc.get("created_at", ""))
            comparisons.append(metrics)

        return {
            "runs": comparisons,
            "count": len(comparisons),
        }

    async def get_score_aggregation(
        self,
        run_id: str,
    ) -> Dict[str, Any]:
        """聚合某个 run 下所有 trial 的评分统计"""
        db = get_mongo_db()

        # 获取该 run 的所有 trial ID
        trial_cursor = db["eval_trials"].find({"run_id": run_id}, {"trial_id": 1})
        trial_ids = []
        async for doc in trial_cursor:
            trial_ids.append(doc["trial_id"])

        if not trial_ids:
            return {"run_id": run_id, "scores": {}}

        # 聚合评分
        pipeline = [
            {"$match": {
                "trial_id": {"$in": trial_ids},
            }},
            {"$group": {
                "_id": "$score_name",
                "avg_score": {"$avg": "$score"},
                "min_score": {"$min": "$score"},
                "max_score": {"$max": "$score"},
                "count": {"$sum": 1},
                "effective_count": {"$sum": {"$cond": [{"$in": ["$status", ["passed", "failed"]]}, 1, 0]}},
                "passed_count": {"$sum": {"$cond": [{"$eq": ["$passed", True]}, 1, 0]}},
                "statuses": {"$addToSet": "$status"},
                "reasons": {"$addToSet": "$reason"},
            }},
            {"$sort": {"_id": 1}},
        ]

        score_stats = {}
        async for doc in db["eval_scores"].aggregate(pipeline):
            name = doc["_id"]
            count = doc["count"]
            statuses = [status for status in doc.get("statuses", []) if status]
            effective = any(status in {"passed", "failed"} for status in statuses) or not statuses
            unavailable_status = next(
                (
                    status
                    for status in ("not_configured", "skipped", "error", "unscorable", "not_applicable")
                    if status in statuses
                ),
                None,
            )
            if unavailable_status and not effective:
                score_stats[name] = {
                    "avg_score": 0.0,
                    "min_score": 0.0,
                    "max_score": 0.0,
                    "count": 0,
                    "passed_count": 0,
                    "pass_rate": 0.0,
                    "variance": 0.0,
                    "status": unavailable_status,
                    "reason": next((reason for reason in doc.get("reasons", []) if reason), ""),
                }
                continue
            effective_count = doc.get("effective_count", doc.get("count", 0))
            score_stats[name] = {
                "avg_score": round(doc["avg_score"], 4),
                "min_score": round(doc["min_score"], 4),
                "max_score": round(doc["max_score"], 4),
                "count": effective_count,
                "passed_count": min(doc["passed_count"], effective_count),
                "pass_rate": round(min(doc["passed_count"], effective_count) / max(1, effective_count), 4),
                "variance": round(
                    (doc["max_score"] - doc["min_score"]) ** 2 / 12, 4
                ),  # 近似方差（均匀分布假设）
                "status": "available",
                "reason": "",
                "unscorable_count": statuses.count("unscorable"),
                "not_applicable_count": statuses.count("not_applicable"),
            }

        run_doc = await db["eval_runs"].find_one({"run_id": run_id}, {"dataset_version": 1})

        return {
            "run_id": run_id,
            "scores": score_stats,
            "total_score_dimensions": len(score_stats),
        }

    async def get_claim_summary(self, run_id: str) -> Dict[str, Any]:
        """聚合某个 run 下所有 trial 的 claim-evidence 统计 (5.3)

        从 eval_scores 文档中的 claims 数组提取 verdict 分布。
        """
        db = get_mongo_db()

        # 获取该 run 的所有 trial ID
        trial_cursor = db["eval_trials"].find({"run_id": run_id}, {"trial_id": 1})
        trial_ids = []
        async for doc in trial_cursor:
            trial_ids.append(doc["trial_id"])

        if not trial_ids:
            return {
                "total_claims": 0,
                "supported": 0,
                "weakly_supported": 0,
                "unsupported": 0,
                "contradicted": 0,
                "hallucination_metrics": {
                    "status": "not_available",
                    "eligible_claims": 0,
                    "excluded_claims": 0,
                },
            }

        # 使用 aggregation 展开 claims 数组并按 verdict 分组
        pipeline = [
            {"$match": {"trial_id": {"$in": trial_ids}, "claims": {"$ne": None, "$not": {"$size": 0}}}},
            {"$unwind": "$claims"},
            {"$group": {
                "_id": "$claims.verdict",
                "count": {"$sum": 1},
            }},
        ]

        verdict_counts: Dict[str, int] = {}
        async for doc in db["eval_scores"].aggregate(pipeline):
            verdict = doc["_id"] or "unknown"
            verdict_counts[verdict] = doc["count"]

        total = sum(verdict_counts.values())

        claim_cursor = db["eval_scores"].find(
            {"trial_id": {"$in": trial_ids}, "claims": {"$ne": None}},
            {"claims": 1},
        )
        claims: List[Dict[str, Any]] = []
        async for score_doc in claim_cursor:
            claims.extend(score_doc.get("claims") or [])

        label_versions = sorted({
            str(claim.get("label_version"))
            for claim in claims
            if claim.get("label_version")
        })
        run_doc = await db["eval_runs"].find_one({"run_id": run_id}, {"dataset_version": 1})

        return {
            "total_claims": total,
            "supported": verdict_counts.get("supported", 0),
            "weakly_supported": verdict_counts.get("weakly_supported", 0),
            "unsupported": verdict_counts.get("unsupported", 0),
            "contradicted": verdict_counts.get("contradicted", 0),
            "hallucination_metrics": self.compute_hallucination_metrics(claims),
            "claims": claims,
            "dataset_version": (run_doc or {}).get("dataset_version", ""),
            "label_versions": label_versions,
            "scorer_version": "2.1.0",
        }

    @staticmethod
    def _stddev(values: List[float]) -> float:
        """计算标准差"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _combination(n: int, k: int) -> int:
        """计算组合数 C(n, k)"""
        if k > n or k < 0:
            return 0
        if k == 0 or k == n:
            return 1
        return math.comb(n, k)


# 单例实例
metrics_service = MetricsService()
