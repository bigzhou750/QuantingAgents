"""Skill 配对回归服务。

负责把 baseline/candidate eval run 配成回归组，逐 case 计算 delta，
并按 critical case、安全/确定性断言执行发布门禁。
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_mongo_db
from app.models.eval import (
    SkillCaseDelta,
    SkillRegressionGateResult,
    SkillRegressionGroup,
)
from app.services.eval.runner_service import runner_service
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class SkillRegressionService:
    """Skill 配对回归服务。"""

    COLLECTION = "eval_skill_regression_groups"
    _CRITICAL_SCORERS = {"skill_execution", "safety", "skill_coexistence"}

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("group_id", unique=True)
        await db[self.COLLECTION].create_index("baseline_run_id")
        await db[self.COLLECTION].create_index("candidate_run_id")
        await db[self.COLLECTION].create_index("skill_name")
        self._initialized = True

    async def create_group(
        self,
        baseline_run_id: str,
        candidate_run_id: str,
        created_by: str = "",
    ) -> SkillRegressionGroup:
        """创建配对回归组。"""
        db = get_mongo_db()
        baseline = await db["eval_runs"].find_one({"run_id": baseline_run_id})
        candidate = await db["eval_runs"].find_one({"run_id": candidate_run_id})
        if not baseline or not candidate:
            raise ValueError("baseline/candidate run not found")
        if baseline.get("dataset_id") != candidate.get("dataset_id"):
            raise ValueError("baseline/candidate runs must share the same dataset")
        if baseline.get("dataset_version") != candidate.get("dataset_version"):
            raise ValueError("baseline/candidate runs must share the same dataset version")

        skill_eval = dict((candidate.get("config") or {}).get("skill_eval") or {})
        runtime_skill_eval = dict(skill_eval)
        runtime_skill_eval.pop("exclude_skills", None)
        runtime_skill_eval.pop("include_skills", None)
        skill_name = str(skill_eval.get("skill_name") or "")
        if not skill_name:
            raise ValueError("candidate run must configure skill_eval.skill_name")

        critical_cases = await self._collect_critical_cases(
            candidate.get("dataset_id"),
            candidate.get("dataset_version"),
        )
        group = SkillRegressionGroup(
            group_id=f"sr_{uuid.uuid4().hex[:12]}",
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            dataset_id=baseline.get("dataset_id", ""),
            dataset_version=baseline.get("dataset_version", ""),
            skill_name=skill_name,
            baseline_skill_version=str(
                (skill_eval.get("skill_versions") or {}).get("baseline", "")
            ),
            candidate_skill_version=str(
                (skill_eval.get("skill_versions") or {}).get("candidate", "")
            ),
            model_version=str(skill_eval.get("model_version") or ""),
            scorer_versions={},
            critical_cases=critical_cases,
            status="pending",
            created_by=created_by,
        )
        doc = group.model_dump(by_alias=True, exclude={"id"})
        await db[self.COLLECTION].insert_one(doc)
        return group

    async def compute_deltas(
        self,
        group_id: str,
    ) -> SkillRegressionGroup:
        """计算并保存逐 case delta。"""
        db = get_mongo_db()
        group = await self.get_group(group_id)
        if not group:
            raise ValueError(f"Skill regression group {group_id} not found")

        baseline_trials = await self._trials_by_case(group.baseline_run_id)
        candidate_trials = await self._trials_by_case(group.candidate_run_id)
        case_names = {}
        for case_id, trials in baseline_trials.items():
            if not trials:
                case_names[case_id] = case_id
                continue
            snapshot = trials[0].get("case_snapshot") or {}
            case_names[case_id] = str(snapshot.get("name", case_id)) if isinstance(snapshot, dict) else case_id
        all_case_ids = sorted(set(baseline_trials) | set(candidate_trials))
        deltas: List[SkillCaseDelta] = []
        scorer_versions: Dict[str, str] = {}

        for case_id in all_case_ids:
            b_trials = baseline_trials.get(case_id, [])
            c_trials = candidate_trials.get(case_id, [])
            b_scores, b_dims = await self._aggregate_trial_scores(b_trials)
            c_scores, c_dims = await self._aggregate_trial_scores(c_trials)
            b_meta = self._aggregate_trial_meta(b_trials)
            c_meta = self._aggregate_trial_meta(c_trials)
            scorer_versions.update(b_scores.get("_scorer_versions", {}))
            scorer_versions.update(c_scores.get("_scorer_versions", {}))
            dims = sorted((set(b_dims) | set(c_dims)) - {"_scorer_versions"})
            dimension_deltas = {}
            regressed_dims = []
            reasons = []
            for dim in dims:
                delta = c_dims.get(dim, 0.0) - b_dims.get(dim, 0.0)
                dimension_deltas[dim] = round(delta, 4)
                if delta < -0.001:
                    regressed_dims.append(dim)
                    if dim in self._CRITICAL_SCORERS:
                        reasons.append(f"{dim} 在关键维度回退 {delta:.2%}")
            regressed = c_scores["avg"] < b_scores["avg"] - 0.001 or bool(regressed_dims)
            deltas.append(SkillCaseDelta(
                case_id=case_id,
                case_name=case_names.get(case_id, case_id),
                critical=case_id in set(group.critical_cases),
                baseline_score=round(b_scores["avg"], 4),
                candidate_score=round(c_scores["avg"], 4),
                delta=round(c_scores["avg"] - b_scores["avg"], 4),
                baseline_latency_ms=round(b_meta["latency"], 1),
                candidate_latency_ms=round(c_meta["latency"], 1),
                baseline_cost_usd=round(b_meta["cost"], 6),
                candidate_cost_usd=round(c_meta["cost"], 6),
                dimension_deltas=dimension_deltas,
                regressed=regressed,
                regressed_dimensions=regressed_dims,
                reasons=reasons,
                failure_trial_ids=[
                    str(t.get("trial_id", ""))
                    for t in (b_trials + c_trials)
                    if t.get("status") in {"failed", "timeout"}
                ],
                baseline_trial_ids=[t.get("trial_id", "") for t in b_trials],
                candidate_trial_ids=[t.get("trial_id", "") for t in c_trials],
            ))

        group.per_case_deltas = deltas
        group.scorer_versions = scorer_versions
        group.status = "computed"
        group.updated_at = now_tz()
        await db[self.COLLECTION].update_one(
            {"group_id": group_id},
            {
                "$set": {
                    "per_case_deltas": [d.model_dump(by_alias=True) for d in deltas],
                    "scorer_versions": scorer_versions,
                    "status": "computed",
                    "updated_at": now_tz(),
                }
            },
        )
        return group

    async def evaluate_gate(self, group_id: str) -> SkillRegressionGroup:
        """执行 critical 回归门禁。"""
        db = get_mongo_db()
        group = await self.get_group(group_id)
        if not group:
            raise ValueError(f"Skill regression group {group_id} not found")
        if not group.per_case_deltas:
            group = await self.compute_deltas(group_id)

        blocks: List[Dict[str, Any]] = []
        checks: List[Dict[str, Any]] = []
        critical_deltas = [d for d in group.per_case_deltas if d.critical]
        critical_regressed = [d for d in critical_deltas if d.regressed]
        checks.append({
            "name": "critical_cases",
            "passed": not critical_regressed,
            "detail": len(critical_regressed),
        })
        if critical_regressed:
            blocks.append({
                "name": "critical_case_regression",
                "cases": [d.case_id for d in critical_regressed],
                "detail": [d.reasons for d in critical_regressed],
            })

        for d in group.per_case_deltas:
            for dim in ("skill_execution", "safety"):
                if d.dimension_deltas.get(dim, 0.0) < -0.05:
                    blocks.append({
                        "name": f"{dim}_regression",
                        "case_id": d.case_id,
                        "delta": d.dimension_deltas[dim],
                    })
                    break

        passed = not blocks
        gate = SkillRegressionGateResult(
            passed=passed,
            enabled=True,
            blocks=blocks,
            checks=checks,
        )
        group.gate_result = gate
        group.status = "gate_passed" if passed else "gate_failed"
        group.updated_at = now_tz()
        await db[self.COLLECTION].update_one(
            {"group_id": group_id},
            {
                "$set": {
                    "gate_result": gate.model_dump(by_alias=True),
                    "status": group.status,
                    "updated_at": now_tz(),
                }
            },
        )
        return group

    async def override_group(
        self,
        group_id: str,
        *,
        allowed: bool,
        reason: str,
        overridden_by: str,
    ) -> SkillRegressionGroup:
        """管理员显式覆盖回归门禁并留痕。"""
        db = get_mongo_db()
        group = await self.get_group(group_id)
        if not group:
            raise ValueError(f"Skill regression group {group_id} not found")
        group.override = {
            "allowed": allowed,
            "reason": reason,
            "overridden_by": overridden_by,
            "overridden_at": now_tz().isoformat(),
        }
        if allowed:
            group.gate_result = SkillRegressionGateResult(
                passed=True,
                enabled=True,
                blocks=[],
                checks=[{"name": "admin_override", "passed": True, "detail": reason}],
            )
            group.status = "gate_passed"
        else:
            group.status = "gate_failed"
        group.updated_at = now_tz()
        await db[self.COLLECTION].update_one(
            {"group_id": group_id},
            {
                "$set": {
                    "override": group.override,
                    "gate_result": group.gate_result.model_dump(by_alias=True),
                    "status": group.status,
                    "updated_at": now_tz(),
                }
            },
        )
        return group

    async def get_group(self, group_id: str) -> Optional[SkillRegressionGroup]:
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one({"group_id": group_id})
        if not doc:
            return None
        return SkillRegressionGroup(**doc)

    async def list_groups(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> List[SkillRegressionGroup]:
        db = get_mongo_db()
        cursor = db[self.COLLECTION].find().sort("created_at", -1).skip(skip).limit(limit)
        return [SkillRegressionGroup(**doc) async for doc in cursor]

    async def _collect_critical_cases(
        self,
        dataset_id: str,
        dataset_version: str,
    ) -> List[str]:
        from app.services.eval.dataset_service import dataset_service

        cases = await dataset_service.list_cases(
            dataset_id,
            limit=2000,
            version=dataset_version,
        )
        result = []
        for case in cases:
            skill_eval = case.get("skill_eval") or (case.get("scoring_criteria") or {}).get("skill_eval")
            if isinstance(skill_eval, dict) and skill_eval.get("critical"):
                result.append(str(case.get("case_id", "")))
        return result

    async def _trials_by_case(self, run_id: str) -> Dict[str, List[Dict[str, Any]]]:
        db = get_mongo_db()
        result: Dict[str, List[Dict[str, Any]]] = {}
        cursor = db["eval_trials"].find({"run_id": run_id})
        async for doc in cursor:
            result.setdefault(str(doc.get("case_id", "")), []).append(doc)
        return result

    async def _aggregate_trial_scores(
        self,
        trials: List[Dict[str, Any]],
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        db = get_mongo_db()
        scores_by_trial: Dict[str, List[Dict[str, Any]]] = {}
        trial_ids = [str(t.get("trial_id", "")) for t in trials if t.get("trial_id")]
        if trial_ids:
            cursor = db["eval_scores"].find({"trial_id": {"$in": trial_ids}})
            async for score in cursor:
                scores_by_trial.setdefault(str(score.get("trial_id", "")), []).append(score)

        dimension_sums: Dict[str, float] = {}
        dimension_counts: Dict[str, int] = {}
        scorer_versions: Dict[str, str] = {}
        total_score = 0.0
        scored_trials = 0
        for trial in trials:
            if trial.get("status") != "completed":
                continue
            scores = [
                s for s in scores_by_trial.get(str(trial.get("trial_id", "")), [])
                if s.get("status") in {"passed", "failed"}
            ]
            if not scores:
                continue
            trial_total = 0.0
            for score in scores:
                name = str(score.get("score_name", "unknown"))
                value = float(score.get("score", 0.0))
                dimension_sums[name] = dimension_sums.get(name, 0.0) + value
                dimension_counts[name] = dimension_counts.get(name, 0) + 1
                scorer_versions[name] = str(score.get("scorer_version", ""))
                trial_total += value
            total_score += trial_total / max(1, len(scores))
            scored_trials += 1

        avg = total_score / max(1, scored_trials)
        dims = {
            name: round(dimension_sums[name] / max(1, dimension_counts[name]), 4)
            for name in dimension_sums
        }
        dims["_scorer_versions"] = scorer_versions
        return {"avg": avg, "count": scored_trials}, dims

    @staticmethod
    def _aggregate_trial_meta(trials: List[Dict[str, Any]]) -> Dict[str, float]:
        latencies = [
            float(t.get("latency_ms") or 0.0)
            for t in trials
            if t.get("status") == "completed"
        ]
        costs = [
            float(t.get("cost_usd") or 0.0)
            for t in trials
            if t.get("status") == "completed"
        ]
        return {
            "latency": sum(latencies) / max(1, len(latencies)),
            "cost": sum(costs) / max(1, len(costs)),
        }


skill_regression_service = SkillRegressionService()
