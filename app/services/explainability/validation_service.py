"""解释一致性校验服务。

比较解释、决策记录和证据，输出 consistent/inconsistent/unverifiable。
"""

import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.models.decision import (
    ExplanationStatus,
    ExplanationValidation,
    LayeredExplanation,
)
from app.utils.timezone import now_tz


def _as_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value or {}


def _explanation_text(explanation: Any) -> str:
    data = _as_dict(explanation)
    return " ".join(
        str(data.get(layer, {}).get("text") or "")
        for layer in ("developer", "business", "user")
    )


class ExplanationValidator:
    """基于规则的解释一致性校验器。"""

    VERSION = "1.0.0"

    def validate(
        self,
        explanation: Any,
        decision: Any,
        *,
        evidence_texts: Optional[List[str]] = None,
        output_text: str = "",
    ) -> ExplanationValidation:
        record = _as_dict(decision)
        explanation_data = _as_dict(explanation)
        if not record or not explanation_data:
            return self._result(
                explanation_data,
                record,
                ExplanationStatus.UNVERIFIABLE,
                "缺少决策记录或解释，无法校验",
                0.0,
            )

        reason = str(record.get("selection_reason") or "")
        if reason in {"candidates_unavailable", "reason_unavailable"}:
            return self._result(
                explanation_data,
                record,
                ExplanationStatus.UNVERIFIABLE,
                "决策缺少候选或选择依据，解释只能标记为不可验证",
                0.4,
            )

        selected = str(record.get("selected_option") or "")
        conclusion = str(record.get("conclusion") or "").strip()
        if not selected or not conclusion:
            return self._result(
                explanation_data,
                record,
                ExplanationStatus.UNVERIFIABLE,
                "决策记录缺少最终选中项或结论",
                0.4,
            )

        text = _explanation_text(explanation_data)
        missing = []
        if selected and selected not in text:
            missing.append("解释未包含最终选中项")
        if conclusion and conclusion[:20] and conclusion[:20] not in text:
            missing.append("解释未包含决策结论")

        contradiction = self._detect_contradiction(conclusion, text)
        if contradiction:
            return self._result(
                explanation_data,
                record,
                ExplanationStatus.INCONSISTENT,
                f"解释与决策结论冲突：{contradiction}",
                0.9,
            )
        if missing:
            return self._result(
                explanation_data,
                record,
                ExplanationStatus.INCONSISTENT,
                "；".join(missing),
                0.8,
            )

        evidence_ids = record.get("evidence_ids") or []
        if evidence_ids and not (evidence_texts or output_text):
            return self._result(
                explanation_data,
                record,
                ExplanationStatus.UNVERIFIABLE,
                "决策记录了证据引用，但当前没有证据或输出用于校验",
                0.5,
            )

        return self._result(
            explanation_data,
            record,
            ExplanationStatus.CONSISTENT,
            "解释与决策记录一致",
            0.9,
        )

    @staticmethod
    def should_require_review(validation: Any, risk_level: str = "low") -> bool:
        data = _as_dict(validation)
        status = data.get("status")
        return status == ExplanationStatus.INCONSISTENT.value and risk_level in {
            "high",
            "critical",
        }

    @staticmethod
    def _detect_contradiction(conclusion: str, explanation_text: str) -> str:
        conclusion = str(conclusion or "")
        if not conclusion:
            return ""
        negations = []
        if any(word in explanation_text for word in ("未采用", "没有依据", "不适用于")):
            negations.append("解释包含否定性表述")
        if "买入" in conclusion and "卖出" in explanation_text:
            return "结论为买入但解释出现卖出"
        if "卖出" in conclusion and "买入" in explanation_text:
            return "结论为卖出但解释出现买入"
        return "；".join(negations)

    @staticmethod
    def _result(
        explanation: Dict[str, Any],
        decision: Dict[str, Any],
        status: ExplanationStatus,
        reason: str,
        confidence: float,
    ) -> ExplanationValidation:
        return ExplanationValidation(
            validation_id=f"val_{uuid.uuid4().hex[:12]}",
            explanation_id=str(explanation.get("explanation_id") or ""),
            business_id=explanation.get("business_id") or decision.get("business_id"),
            task_id=explanation.get("task_id") or decision.get("task_id"),
            session_id=explanation.get("session_id") or decision.get("session_id"),
            decision_id=explanation.get("decision_id") or decision.get("decision_id"),
            status=status,
            reason=reason,
            confidence=confidence,
            validator_version=ExplanationValidator.VERSION,
            created_at=now_tz(),
        )


explanation_validator = ExplanationValidator()
