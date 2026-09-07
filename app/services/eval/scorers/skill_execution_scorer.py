"""Skill 执行评分器。

执行断言优先使用程序规则检查必需/禁止工具、文件、schema、公式和状态变更，
开放类输出质量仍交给其他 scorer。
"""

from typing import Any, Dict, List, Optional

from app.models.eval import ScoreSource, ScoreStatus
from app.services.eval.scorers.base import BaseScorer, ScoreResult


class SkillExecutionScorer(BaseScorer):
    """确定性 Skill 执行断言。"""

    @property
    def name(self) -> str:
        return "skill_execution"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.RULE_BASED

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
        asserts = dict(skill_eval.get("execution_asserts") or {})
        if not asserts:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="Skill 评测未配置执行断言",
                source=self.source,
                version=self.version,
                status=ScoreStatus.NOT_CONFIGURED,
            )

        tool_calls = self._extract_tool_calls(trace_events, trial_data)
        used_tools = {call.get("name", "") for call in tool_calls}
        checks = []  # (name, passed, detail)
        reasons: List[str] = []

        required_tools = [str(x) for x in asserts.get("required_tools", [])]
        missing_tools = [name for name in required_tools if name not in used_tools]
        checks.append(("required_tools", not missing_tools, missing_tools))
        if missing_tools:
            reasons.append(f"缺少必需工具: {', '.join(missing_tools)}")

        forbidden_tools = [str(x) for x in asserts.get("forbidden_tools", [])]
        used_forbidden = [name for name in forbidden_tools if name in used_tools]
        checks.append(("forbidden_tools", not used_forbidden, used_forbidden))
        if used_forbidden:
            reasons.append(f"调用了禁止工具: {', '.join(used_forbidden)}")

        required_files = [str(x) for x in asserts.get("required_files", [])]
        touched_files = self._extract_touched_files(trace_events, trial_data)
        missing_files = [name for name in required_files if name not in touched_files]
        checks.append(("required_files", not missing_files, missing_files))
        if missing_files:
            reasons.append(f"缺少必需文件: {', '.join(missing_files)}")

        for index, check in enumerate(asserts.get("schema_checks", []) or []):
            passed, detail = self._check_schema(check, trial_data)
            checks.append((f"schema_{index}", passed, detail))
            if not passed:
                reasons.append(f"schema 检查 {index} 失败: {detail}")

        for index, check in enumerate(asserts.get("formula_checks", []) or []):
            passed, detail = self._check_formula(check, trial_data)
            checks.append((f"formula_{index}", passed, detail))
            if not passed:
                reasons.append(f"formula 检查 {index} 失败: {detail}")

        for index, check in enumerate(asserts.get("state_checks", []) or []):
            passed, detail = self._check_state(check, trial_data)
            checks.append((f"state_{index}", passed, detail))
            if not passed:
                reasons.append(f"状态检查 {index} 失败: {detail}")

        output_structure = asserts.get("output_structure") or {}
        missing_keys = [
            key for key in output_structure.get("required_keys", [])
            if not self._has_output_key(trial_data, key)
        ]
        checks.append(("output_structure", not missing_keys, missing_keys))
        if missing_keys:
            reasons.append(f"输出缺少字段: {', '.join(missing_keys)}")

        max_steps = int(asserts.get("max_expected_steps", 20) or 20)
        step_ok = len(tool_calls) <= max_steps
        checks.append(("step_budget", step_ok, len(tool_calls)))
        if not step_ok:
            reasons.append(f"工具步骤数 {len(tool_calls)} 超过预算 {max_steps}")

        passed_checks = sum(1 for _, passed, _ in checks if passed)
        score = passed_checks / max(1, len(checks))
        reason_text = "; ".join(reasons) if reasons else "全部执行断言通过"
        return ScoreResult(
            score_name=self.name,
            score=round(score, 4),
            passed=score == 1.0,
            reason=reason_text,
            confidence=0.95,
            source=self.source,
            version=self.version,
            status=ScoreStatus.PASSED if score == 1.0 else ScoreStatus.FAILED,
            raw_output={
                "used_tools": sorted(used_tools),
                "touched_files": sorted(touched_files),
                "checks": [{"name": n, "passed": p, "detail": d} for n, p, d in checks],
            },
        )

    @staticmethod
    def _extract_tool_calls(
        trace_events: List[Dict[str, Any]],
        trial_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        calls: List[Dict[str, Any]] = []
        for event in trace_events or []:
            if event.get("event_type") != "tool_call":
                continue
            data = event.get("data") or {}
            calls.append({
                "name": str(data.get("tool") or data.get("tool_name") or "unknown"),
                "arguments": data.get("arguments") or {},
            })
        output_data = trial_data.get("output_data") or {}
        for item in output_data.get("tool_trail") or []:
            calls.append({
                "name": str(item.get("tool") or item.get("name") or "unknown"),
                "arguments": item.get("arguments") or {},
            })
        return calls

    @staticmethod
    def _extract_touched_files(
        trace_events: List[Dict[str, Any]],
        trial_data: Dict[str, Any],
    ) -> set[str]:
        paths: set[str] = set()
        for event in trace_events or []:
            if event.get("event_type") != "tool_call":
                continue
            args = (event.get("data") or {}).get("arguments") or {}
            for key in ("path", "file_path", "filename", "output_path", "file"):
                if args.get(key):
                    paths.add(str(args[key]))
        output_data = trial_data.get("output_data") or {}
        for path in output_data.get("files") or []:
            paths.add(str(path.get("path") if isinstance(path, dict) else path))
        return paths

    @staticmethod
    def _check_schema(check: Dict[str, Any], trial_data: Dict[str, Any]) -> tuple[bool, str]:
        field = str(check.get("field", ""))
        required = bool(check.get("required", False))
        if field and required and not SkillExecutionScorer._has_output_key(trial_data, field):
            return False, f"缺少字段 {field}"
        if not field and check.get("missing_field"):
            return False, f"不应出现字段 {check['missing_field']}"
        return True, ""

    @staticmethod
    def _check_formula(check: Dict[str, Any], trial_data: Dict[str, Any]) -> tuple[bool, str]:
        maybe_value = SkillExecutionScorer._output_value(trial_data, str(check.get("field", "")))
        if maybe_value is None:
            return False, f"缺少公式字段 {check.get('field')}"
        expected = check.get("expected")
        operation = str(check.get("operation", "eq"))
        try:
            value, expected_value = float(maybe_value), float(expected)
        except (TypeError, ValueError):
            return False, f"{maybe_value!r} 与 {expected!r} 不可数值比较"
        ok = {
            "eq": abs(value - expected_value) <= float(check.get("tolerance", 0.0)),
            "gt": value > expected_value,
            "gte": value >= expected_value,
            "lt": value < expected_value,
            "lte": value <= expected_value,
        }.get(operation, False)
        return ok, f"{field}={value} 不满足 {operation} {expected_value}" if not ok else ""

    @staticmethod
    def _check_state(check: Dict[str, Any], trial_data: Dict[str, Any]) -> tuple[bool, str]:
        loaded = trial_data.get("state_before") or {}
        after = trial_data.get("state_after") or {}
        key = str(check.get("field", ""))
        if not key:
            return True, ""
        before = loaded.get(key)
        current = after.get(key)
        if check.get("expected_change") == True and before == current:
            return False, f"状态字段 {key} 未变化"
        if check.get("expected_value") is not None and current != check.get("expected_value"):
            return False, f"状态字段 {key}={current!r} 不等于 {check.get('expected_value')!r}"
        return True, ""

    @staticmethod
    def _has_output_key(trial_data: Dict[str, Any], key: str) -> bool:
        return SkillExecutionScorer._output_value(trial_data, key) is not None

    @staticmethod
    def _output_value(trial_data: Dict[str, Any], dotted_key: str) -> Any:
        output_data = trial_data.get("output_data") or {}
        current: Any = output_data
        for part in dotted_key.split("."):
            if not isinstance(current, dict) or part not in current:
                # 允许从 content JSON 中查找。
                content = output_data.get("content")
                if isinstance(content, dict) and part in content:
                    current = content[part]
                    continue
                return None
            current = current[part]
        return current
