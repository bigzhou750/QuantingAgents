"""
输出完整性评分器

检查 Agent 输出的完整性和质量，包括：
- 输出长度检查
- 必需字段检查
- 格式检查
- 内容质量基础检查
"""

import logging
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class OutputCompletenessScorer(BaseScorer):
    """输出完整性评分器"""

    @property
    def name(self) -> str:
        return "output_completeness"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.RULE_BASED

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """执行输出完整性评分"""
        checks = []
        reasons = []

        output_data = trial_data.get("output_data")

        # 1. 输出存在性
        if not output_data:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="缺少输出数据",
                confidence=1.0,
                source=self.source,
                version=self.version,
            )

        config = case_config or {}

        # 2. 输出类型检查
        expected_type = config.get("expected_output_type")
        if expected_type:
            if isinstance(output_data, dict) and expected_type == "dict":
                checks.append(True)
            elif isinstance(output_data, str) and expected_type == "str":
                checks.append(True)
            elif isinstance(output_data, list) and expected_type == "list":
                checks.append(True)
            else:
                checks.append(False)
                reasons.append(f"输出类型不匹配，期望 {expected_type}")
        else:
            checks.append(True)

        # 3. 必需字段检查（仅对 dict 类型）
        if isinstance(output_data, dict):
            required_fields = config.get("required_fields", [])
            missing_fields = [f for f in required_fields if f not in output_data]
            if missing_fields:
                checks.append(False)
                reasons.append(f"缺少必需字段: {', '.join(missing_fields)}")
            else:
                checks.append(True)

        # 4. 最小长度检查
        min_length = config.get("min_output_length", 10)
        content_str = str(output_data)
        if len(content_str) < min_length:
            checks.append(False)
            reasons.append(f"输出长度 {len(content_str)} 小于最小要求 {min_length}")
        else:
            checks.append(True)

        # 5. 最大长度检查（可选）
        max_length = config.get("max_output_length")
        if max_length and len(content_str) > max_length:
            checks.append(False)
            reasons.append(f"输出长度 {len(content_str)} 超过最大限制 {max_length}")
        elif max_length:
            checks.append(True)

        # 6. 空值检查
        if isinstance(output_data, dict):
            empty_values = [k for k, v in output_data.items() if v is None or v == "" or v == []]
            if empty_values:
                checks.append(False)
                reasons.append(f"存在空值字段: {', '.join(empty_values[:5])}")
            else:
                checks.append(True)
        else:
            checks.append(True)

        # 7. Final Report 事件检查（从 trace 中查找）
        has_final_report = any(
            e.get("event_type") == "final_report" for e in trace_events
        )
        if has_final_report:
            checks.append(True)
        else:
            checks.append(False)
            reasons.append("缺少 final_report 事件")

        # 计算分数
        passed_checks = sum(1 for c in checks if c)
        total_checks = len(checks)
        score = self._calculate_score(passed_checks, total_checks)

        reason_text = "; ".join(reasons) if reasons else f"输出完整性检查通过 ({passed_checks}/{total_checks})"

        return ScoreResult(
            score_name=self.name,
            score=score,
            passed=score >= 0.7,
            reason=reason_text,
            confidence=1.0,
            source=self.source,
            version=self.version,
        )
