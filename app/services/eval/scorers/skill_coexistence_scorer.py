"""Skill 共存冲突评分器。

基于完整的 Skill 集合执行结果和 trace，检测抢触发、错误组合以及目标
Skill 对相邻 Skill 成功率的负面影响。
"""

from typing import Any, Dict, List, Optional

from app.models.eval import ScoreSource, ScoreStatus
from app.services.eval.scorers.base import BaseScorer, ScoreResult


class SkillCoexistenceScorer(BaseScorer):
    """检查目标 Skill 与相邻 Skill 的共存影响。"""

    @property
    def name(self) -> str:
        return "skill_coexistence"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.TRACE

    @property
    def version(self) -> str:
        return "1.0.0"

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        skill_eval = dict((case_config or {}).get("skill_eval") or {})
        coexistence = dict(skill_eval.get("coexistence") or {})
        if not coexistence:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="Skill 评测未配置共存场景",
                source=self.source,
                version=self.version,
                status=ScoreStatus.NOT_CONFIGURED,
            )

        checks = []
        reasons: List[str] = []
        metrics = trial_data.get("coexistence") or trial_data.get("coexistence_metrics") or {}

        if metrics:
            baseline = dict(metrics.get("baseline_neighbor_success") or {})
            candidate = dict(metrics.get("candidate_neighbor_success") or {})
            max_drop = float(coexistence.get("max_neighbor_success_drop", 0.1) or 0.1)
            neighbor_skills = [str(x) for x in coexistence.get("neighbor_skills", [])]
            for neighbor in neighbor_skills:
                drop = float(baseline.get(neighbor, 1.0) or 0.0) - float(candidate.get(neighbor, 0.0) or 0.0)
                ok = drop <= max_drop
                checks.append((f"neighbor_{neighbor}", ok, round(drop, 4)))
                if not ok:
                    reasons.append(f"相邻 Skill {neighbor} 成功率下降 {drop:.2%}")

            target_success = metrics.get("target_success")
            if target_success is not None and target_success is not True:
                ok = float(target_success) == 1.0
                checks.append(("target_success", ok, target_success))
                if not ok:
                    reasons.append(f"目标 Skill 在共存集合中成功率为 {target_success}")
        else:
            executed = self._executed_skills(trace_events)
            expected_target = skill_eval.get("skill_name") or ""
            if expected_target and coexistence.get("conflict_scenario"):
                ok = expected_target in executed
                checks.append(("target_loaded", ok, expected_target))
                if not ok:
                    reasons.append(f"共存场景下目标 Skill {expected_target} 未加载")

            forbidden_overlaps = [str(x) for x in coexistence.get("forbidden_overlaps", [])]
            touched = self._touched_tools_files(trace_events)
            invalid_overlaps = [token for token in forbidden_overlaps if token in touched]
            checks.append(("forbidden_overlap", not invalid_overlaps, invalid_overlaps))
            if invalid_overlaps:
                reasons.append(f"检测到禁止共享: {', '.join(invalid_overlaps)}")

        if not checks:
            checks.append(("coexistence_configured", False, "缺少可比 metrics/trace"))
            reasons.append("共存评测缺少可比 metrics/trace")

        passed_checks = sum(1 for _, ok, _ in checks if ok)
        score = passed_checks / max(1, len(checks))
        return ScoreResult(
            score_name=self.name,
            score=round(score, 4),
            passed=score == 1.0,
            reason="; ".join(reasons) if reasons else "共存场景未发现冲突",
            confidence=0.85,
            source=self.source,
            version=self.version,
            status=ScoreStatus.PASSED if score == 1.0 else ScoreStatus.FAILED,
            raw_output={
                "checks": [{"name": n, "passed": p, "detail": d} for n, p, d in checks],
                "executed_skills": sorted(self._executed_skills(trace_events)),
            },
        )

    @staticmethod
    def _executed_skills(trace_events: List[Dict[str, Any]]) -> set[str]:
        names: set[str] = set()
        for event in trace_events or []:
            if event.get("event_type") != "skill_execute":
                continue
            data = event.get("data") or {}
            if data.get("skill"):
                names.add(str(data["skill"]))
        return names

    @staticmethod
    def _touched_tools_files(trace_events: List[Dict[str, Any]]) -> set[str]:
        touched: set[str] = set()
        for event in trace_events or []:
            if event.get("event_type") != "tool_call":
                continue
            data = event.get("data") or {}
            tool = data.get("tool") or data.get("tool_name")
            if tool:
                touched.add(str(tool))
            args = data.get("arguments") or {}
            for key in ("path", "file_path", "filename", "output_path", "file"):
                if args.get(key):
                    touched.add(str(args[key]))
        return touched
