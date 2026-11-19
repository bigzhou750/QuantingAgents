"""Skill 路由评分器。

把 EvalCase 中的 expected_route 与 trace 中的 skill_route/skill_execute
事件比较，区分命中、漏触发、误触发和“加载了但未生效”的静默绕过。
"""

from typing import Any, Dict, List, Optional

from app.models.eval import ScoreSource, ScoreStatus
from app.services.eval.scorers.base import BaseScorer, ScoreResult


class SkillRouteScorer(BaseScorer):
    """基于 route/execute 事件的 Skill 路由评分器。"""

    @property
    def name(self) -> str:
        return "skill_route"

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
        expectation = dict(skill_eval.get("route_expectation") or {})
        should_trigger = [str(x) for x in expectation.get("should_trigger", [])]
        should_not_trigger = [str(x) for x in expectation.get("should_not_trigger", [])]
        if not should_trigger and not should_not_trigger:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="Skill 评测未配置路由断言",
                source=self.source,
                version=self.version,
                status=ScoreStatus.NOT_CONFIGURED,
            )

        selected, executed = self._extract_route_state(trace_events)
        checks = []
        reasons: List[str] = []

        # 正向触发：应触发但未触发。
        missing = [name for name in should_trigger if name not in selected]
        checks.append(("should_trigger", not missing, []))
        if missing:
            reasons.append(f"漏触发 Skill: {', '.join(missing)}")

        # 负向触发：不应触发但被选中。
        false_positives = [name for name in should_not_trigger if name in selected]
        checks.append(("should_not_trigger", not false_positives, false_positives))
        if false_positives:
            reasons.append(f"误触发 Skill: {', '.join(false_positives)}")

        # 静默绕过：有候选/加载声称，但没有 execute 事件。
        silent = [
            name for name in should_trigger
            if name in selected and name not in executed
        ]
        checks.append(("silent_bypass", not silent, silent))
        if silent:
            reasons.append(f"静默绕过 Skill: {', '.join(silent)}")

        passed_checks = sum(1 for _, ok, _ in checks if ok)
        score = passed_checks / max(1, len(checks))
        reason_text = "; ".join(reasons) if reasons else "路由命中且未检测到误触发"
        raw_output = {
            "selected_skills": sorted(selected),
            "executed_skills": sorted(executed),
            "missing": missing,
            "false_positives": false_positives,
            "silent_bypass": silent,
            "checks": [{"name": n, "passed": ok, "detail": d} for n, ok, d in checks],
        }
        return ScoreResult(
            score_name=self.name,
            score=round(score, 4),
            passed=score == 1.0,
            reason=reason_text,
            confidence=0.9,
            source=self.source,
            version=self.version,
            raw_output=raw_output,
            status=ScoreStatus.PASSED if score == 1.0 else ScoreStatus.FAILED,
        )

    @staticmethod
    def _extract_route_state(
        trace_events: List[Dict[str, Any]],
    ) -> tuple[set[str], set[str]]:
        selected: set[str] = set()
        executed: set[str] = set()
        for event in trace_events or []:
            event_type = event.get("event_type", "")
            data = event.get("data") or {}
            if event_type not in {"skill_route", "skill_execute"}:
                continue
            raw_names = (
                data.get("selected_skills")
                or data.get("candidates")
                or data.get("candidate_skills")
                or data.get("skill")
            )
            names = (
                [str(x) for x in raw_names]
                if isinstance(raw_names, list)
                else ([str(raw_names)] if raw_names else [])
            )
            if data.get("selected") or event_type == "skill_execute" or data.get("skill"):
                selected.update(names)
            if event_type == "skill_execute":
                executed.update(names)
        return selected, executed
