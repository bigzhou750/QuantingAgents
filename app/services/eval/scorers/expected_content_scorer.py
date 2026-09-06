"""
Expected content scorer

把 Case 的 expected_output 和 scoring_criteria 中定义的必含内容、结构、
禁止内容和工具类型转成可验证的输出覆盖检查，避免参考答案只保存不消费。
"""

import logging
from typing import Optional, Dict, List, Any

from app.models.eval import ScoreSource, ScoreStatus
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class ExpectedContentScorer(BaseScorer):
    """基于 Case 参考答案和评分标准的输出覆盖评分器。"""

    @property
    def name(self) -> str:
        return "expected_content"

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
        config = case_config or {}
        expected_output = config.get("expected_output") or {}
        if isinstance(expected_output, str):
            try:
                expected_output = __import__("json").loads(expected_output)
            except Exception:
                expected_output = {"must_include": [expected_output]}

        output_data = trial_data.get("output_data", {})
        if isinstance(output_data, dict):
            output_text = output_data.get("content", "") or output_data.get("result", "")
        else:
            output_text = str(output_data or "")

        must_include = expected_output.get("must_include", []) if isinstance(expected_output, dict) else []
        required_fields = config.get("required_fields", [])
        required_sections = config.get("required_sections", [])
        forbidden_phrases = config.get("forbidden_phrases", [])
        required_tool_types = config.get("required_tool_types", [])

        check_count = 0
        passed_count = 0
        reasons = []
        raw_output = {}

        if must_include:
            missing = [item for item in must_include if str(item) not in output_text]
            check_count += 1
            passed_count += int(not missing)
            reasons.extend(f"缺少必含内容: {item}" for item in missing)
            raw_output["missing_must_include"] = missing

        if required_fields:
            present = [field for field in required_fields if isinstance(output_data, dict) and output_data.get(field) not in (None, "", [])]
            missing_fields = [field for field in required_fields if field not in present]
            check_count += 1
            passed_count += int(not missing_fields)
            reasons.extend(f"缺少必含字段: {field}" for field in missing_fields)
            raw_output["missing_required_fields"] = missing_fields

        if required_sections:
            missing_sections = [section for section in required_sections if section not in output_text]
            check_count += 1
            passed_count += int(not missing_sections)
            reasons.extend(f"缺少结构章节: {section}" for section in missing_sections)
            raw_output["missing_required_sections"] = missing_sections

        if forbidden_phrases:
            forbidden_hits = [phrase for phrase in forbidden_phrases if phrase in output_text]
            check_count += 1
            passed_count += int(not forbidden_hits)
            reasons.extend(f"出现禁止内容: {phrase}" for phrase in forbidden_hits)
            raw_output["forbidden_hits"] = forbidden_hits

        if required_tool_types:
            tool_names = set()
            trail = (output_data.get("tool_trail") or []) if isinstance(output_data, dict) else []
            for item in trail:
                tool = item.get("tool") or item.get("name") or ""
                if tool:
                    tool_names.add(tool)
            for event in trace_events:
                if event.get("event_type") == "tool_call":
                    data = event.get("data", {})
                    tool = data.get("tool_name") or data.get("name") or ""
                    if tool:
                        tool_names.add(tool)
            missing_tools = [t for t in required_tool_types if t not in " ".join(tool_names)]
            check_count += 1
            passed_count += int(not missing_tools)
            reasons.extend(f"缺少工具类型: {t}" for t in missing_tools)
            raw_output["missing_tool_types"] = missing_tools

        if check_count == 0:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="Case 未定义 expected_output 或内容评分标准，维度不适用",
                confidence=0.0,
                source=self.source,
                version=self.version,
                status=ScoreStatus.NOT_APPLICABLE,
                raw_output={"status": "not_applicable"},
            )

        score = passed_count / check_count
        passed = passed_count == check_count
        return ScoreResult(
            score_name=self.name,
            score=score,
            passed=passed,
            reason="; ".join(reasons) if reasons else f"输出覆盖检查通过 ({passed_count}/{check_count})",
            confidence=1.0,
            source=self.source,
            version=self.version,
            status=ScoreStatus.PASSED if passed else ScoreStatus.FAILED,
            raw_output={"checks_total": check_count, "checks_passed": passed_count, **raw_output},
        )
