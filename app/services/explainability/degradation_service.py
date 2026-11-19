"""解释链路故障时的风险分级与降级策略。"""

from typing import Any, Dict, Optional

from app.core.config import settings
from app.models.decision import DecisionStatus
from app.services.explainability.record_service import decision_record_store


class DegradationService:
    """低风险继续、高风险暂停并由人工复核兜底。"""

    RISK_WEIGHTS = {
        "low": 0.1,
        "medium": 0.4,
        "high": 0.8,
        "critical": 0.95,
    }

    @classmethod
    def risk_score(cls, record: Dict[str, Any]) -> float:
        risk_level = str(record.get("risk_level") or "low")
        weight = cls.RISK_WEIGHTS.get(risk_level, 0.4)
        return max(weight, float(record.get("confidence") or 0.0) * weight)

    @classmethod
    def is_high_risk(cls, record: Dict[str, Any]) -> bool:
        return cls.risk_score(record) >= settings.EXPLAINABILITY_HIGH_RISK_THRESHOLD

    async def handle_failure(
        self,
        *,
        task_id: Optional[str],
        session_id: Optional[str],
        business_id: Optional[str],
        decision: Optional[Dict[str, Any]],
        reason: str,
        reviewer: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = decision or {}
        high_risk = self.is_high_risk(record)
        mode = settings.EXPLAINABILITY_MODE
        if high_risk:
            review = await decision_record_store.create_review(
                business_id=business_id,
                task_id=task_id,
                session_id=session_id,
                decision_id=record.get("decision_id"),
                action="pause",
                reason=reason,
                reviewer=reviewer,
            )
            return {
                "mode": "blocked",
                "high_risk": True,
                "reason": reason,
                "review_id": review.get("review_id"),
                "boundary_note": "高风险决策已暂停，等待人工复核",
            }
        return {
            "mode": "degraded",
            "high_risk": False,
            "reason": reason,
            "boundary_note": "解释链路不可用，任务结果已保留并以原始 trace 记录",
        }

    @staticmethod
    def mark_unverified(record: Dict[str, Any]) -> Dict[str, Any]:
        record["status"] = DecisionStatus.UNVERIFIED.value
        record["selection_reason"] = record.get("selection_reason") or "reason_unavailable"
        return record


degradation_service = DegradationService()
