"""决策链生产指标与告警检查服务。"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.decision import (
    DecisionStatus,
    ExplainabilityMetricDoc,
    ExplanationStatus,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class DecisionMetricsService:
    """聚合决策链完整率、解释一致性、证据覆盖、审计延迟和风险暂停。"""

    COLLECTION = "explainability_metrics"

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("metric_id", unique=True)
        await db[self.COLLECTION].create_index("window_start")
        await db[self.COLLECTION].create_index("task_type")
        await db[self.COLLECTION].create_index("risk_level")
        await db[self.COLLECTION].create_index("model_version")
        self._initialized = True

    @staticmethod
    def compute(
        records: List[Dict[str, Any]],
        validations: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        total = max(0, len(records))
        missing = sum(
            1
            for record in records
            if record.get("status")
            in {
                DecisionStatus.UNVERIFIED.value,
                DecisionStatus.DEGRADED.value,
                DecisionStatus.BLOCKED.value,
            }
        )
        consistent = sum(
            1
            for item in validations
            if item.get("status") == ExplanationStatus.CONSISTENT.value
        )
        inconsistent = sum(
            1
            for item in validations
            if item.get("status") == ExplanationStatus.INCONSISTENT.value
        )
        unverifiable = sum(
            1
            for item in validations
            if item.get("status") == ExplanationStatus.UNVERIFIABLE.value
        )
        evidence_covered = sum(
            1 for record in records if record.get("evidence_ids")
        )
        evidence_total = total
        return {
            "decision_nodes": total,
            "missing_decision_nodes": missing,
            "consistent_count": consistent,
            "inconsistent_count": inconsistent,
            "unverifiable_count": unverifiable,
            "evidence_covered": evidence_covered,
            "evidence_total": evidence_total,
            "completeness_rate": round((total - missing) / total, 4) if total else 1.0,
            "consistency_rate": round(consistent / (consistent + inconsistent + unverifiable), 4)
            if (consistent + inconsistent + unverifiable)
            else 1.0,
        }

    async def save_metric(self, metric: ExplainabilityMetricDoc) -> Dict[str, Any]:
        db = get_mongo_db()
        doc = metric.model_dump(by_alias=True, exclude={"id"})
        await db[self.COLLECTION].insert_one(doc)
        return doc

    async def record_task_metrics(
        self,
        *,
        task_id: str,
        business_id: Optional[str] = None,
        session_id: Optional[str] = None,
        task_type: str = "vibe_agent",
        model_version: Optional[str] = None,
        risk_level: str = "",
        high_risk_pauses: int = 0,
    ) -> Dict[str, Any]:
        from app.services.explainability.record_service import decision_record_store

        records = await decision_record_store.list_decision_records(
            business_id=business_id,
            task_id=task_id,
            session_id=session_id,
        )
        validations = await decision_record_store.list_validations(task_id=task_id)
        summary = self.compute(records, validations)
        metric = ExplainabilityMetricDoc(
            metric_id=f"met_{uuid.uuid4().hex[:12]}",
            window_start=now_tz(),
            window_end=now_tz(),
            task_type=task_type,
            model_version=model_version,
            risk_level=risk_level or "all",
            high_risk_pauses=high_risk_pauses,
            **summary,
        )
        return await self.save_metric(metric)

    @staticmethod
    def check_alerts(metric: Dict[str, Any]) -> List[Dict[str, str]]:
        alerts: List[Dict[str, str]] = []
        threshold = settings.EXPLAINABILITY_ALERT_THRESHOLD
        completeness = float(metric.get("completeness_rate") or 1.0)
        consistency = float(metric.get("consistency_rate") or 1.0)
        if completeness < threshold:
            alerts.append(
                {
                    "metric": "decision_chain_completeness",
                    "level": "warning",
                    "message": f"决策链完整率 {completeness:.0%} 低于阈值 {threshold:.0%}",
                }
            )
        if consistency < threshold:
            alerts.append(
                {
                    "metric": "explanation_consistency",
                    "level": "warning",
                    "message": f"解释一致率 {consistency:.0%} 低于阈值 {threshold:.0%}",
                }
            )
        return alerts

    async def get_recent_metrics(self, limit: int = 30) -> List[Dict[str, Any]]:
        cursor = (
            get_mongo_db()[self.COLLECTION]
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def publish_alerts(self, alerts: List[Dict[str, str]]) -> int:
        """把触发的生产决策指标告警写入现有通知渠道。"""
        if not alerts:
            return 0
        try:
            from app.models.notification import NotificationCreate
            from app.services.notifications_service import get_notifications_service

            db = get_mongo_db()
            cursor = db["users"].find(
                {"is_admin": True, "is_active": True},
                {"_id": 0, "user_id": 1},
            )
            user_ids = [str(doc.get("user_id") or "") for doc in await cursor.to_list(length=100)]
            sent = 0
            for user_id in user_ids:
                if not user_id:
                    continue
                for alert in alerts:
                    await get_notifications_service().create_and_publish(
                        NotificationCreate(
                            user_id=user_id,
                            type="alert",
                            title="Agent 决策链指标告警",
                            content=alert.get("message", ""),
                            link="/evaluation/decision-audit",
                            source="explainability_metrics",
                            severity="warning",
                            metadata={"metric": alert.get("metric"), "level": alert.get("level")},
                        )
                    )
                    sent += 1
            return sent
        except Exception as exc:
            logger.warning("failed to publish decision explainability alerts: %s", exc)
            return 0


decision_metrics_service = DecisionMetricsService()
