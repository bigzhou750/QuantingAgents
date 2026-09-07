"""决策记录、解释、校验和人工复核记录存储。"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_mongo_db
from app.models.decision import (
    CandidateOption,
    DecisionRecordDoc,
    DecisionReview,
    DecisionStatus,
    ExplanationValidation,
    LayeredExplanation,
    ReviewStatus,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


def _extract_candidates(payload: Dict[str, Any]) -> List[CandidateOption]:
    raw = payload.get("candidates") or payload.get("options") or []
    candidates: List[CandidateOption] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            candidates.append(CandidateOption(option_id=str(index), label=item))
        elif isinstance(item, dict):
            candidates.append(
                CandidateOption(
                    option_id=str(item.get("id") or item.get("option_id") or index),
                    label=str(item.get("label") or item.get("name") or item.get("tool") or ""),
                    metadata=item.get("metadata") or {},
                    rejected_reason=item.get("rejected_reason") or item.get("reason"),
                )
            )
    return candidates


def normalize_event_to_decision(
    event_type: str,
    payload: Optional[Dict[str, Any]],
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    business_id: Optional[str] = None,
    parent_decision_id: Optional[str] = None,
) -> DecisionRecordDoc:
    """把 Agent 事件归一为结构化决策记录，缺失信息显式标记而不是编造。"""
    payload = payload or {}
    decision_type = "tool" if str(event_type).startswith("tool") else "agent"
    candidates = _extract_candidates(payload)
    selected = (
        payload.get("selected_option")
        or payload.get("selected")
        or payload.get("name")
        or payload.get("tool")
    )
    reason = (
        payload.get("selection_reason")
        or payload.get("rationale")
        or payload.get("reason")
        or ""
    )
    conclusion = (
        payload.get("conclusion")
        or payload.get("decision")
        or payload.get("summary")
        or (payload.get("result") or {}).get("summary")
        or ""
    )
    scenario = str(
        payload.get("scenario")
        or {
            "tool_call": "工具调用决策",
            "tool_result": "工具结果决策",
            "evidence": "证据引用决策",
            "react_summary": "ReAct 总结决策",
            "swarm_status": "Swarm 节点决策",
            "attempt.completed": "任务完成结论",
        }.get(str(event_type), "Agent 决策")
    )

    if decision_type == "tool" and not candidates:
        reason = reason or "candidates_unavailable"
    elif candidates and not reason:
        reason = "reason_unavailable"

    status = DecisionStatus.UNVERIFIED
    if reason and conclusion and selected:
        status = DecisionStatus.CONFIRMED

    evidence_ids = list(payload.get("evidence_ids") or [])
    if payload.get("evidence_id") and payload["evidence_id"] not in evidence_ids:
        evidence_ids.append(str(payload["evidence_id"]))
    if payload.get("trace_event_id") and payload["trace_event_id"] not in evidence_ids:
        evidence_ids.append(str(payload["trace_event_id"]))

    try:
        confidence = float(payload.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    risk_level = str(payload.get("risk_level") or "medium")
    if risk_level not in {"low", "medium", "high", "critical"}:
        risk_level = "medium"
    try:
        sequence = max(0, int(payload.get("sequence", 0)))
    except (TypeError, ValueError):
        sequence = 0

    return DecisionRecordDoc(
        decision_id=str(payload.get("decision_id") or f"dec_{uuid.uuid4().hex[:12]}"),
        sequence=sequence,
        decision_type=decision_type,
        business_id=business_id or payload.get("business_id"),
        task_id=task_id or payload.get("task_id"),
        session_id=session_id or payload.get("session_id"),
        user_id=user_id or payload.get("user_id"),
        scenario=scenario,
        candidates=candidates,
        selected_option=str(selected) if selected else None,
        selection_reason=str(reason or "")[:2000],
        conclusion=str(conclusion or "")[:4000],
        evidence_ids=evidence_ids[:50],
        parent_decision_id=parent_decision_id or payload.get("parent_decision_id"),
        status=status,
        confidence=confidence,
        risk_level=risk_level,
        model_version=payload.get("model_version"),
        strategy_version=payload.get("strategy_version"),
        raw_reasoning_ref=payload.get("raw_reasoning_ref") or payload.get("reasoning_ref"),
    )


def decision_trace_event(record: DecisionRecordDoc) -> Dict[str, Any]:
    """把决策记录转换成 TraceAdapter 可消费的事件字典。"""
    return {
        "type": "decision",
        "business_id": record.business_id,
        "task_id": record.task_id,
        "session_id": record.session_id,
        "data": record.model_dump(mode="json", exclude={"id"}),
    }


class DecisionRecordStore:
    """决策链各集合的统一读写入口。"""

    DECISIONS = "agent_decision_records"
    EXPLANATIONS = "agent_explanations"
    VALIDATIONS = "agent_explanation_validations"
    REVIEWS = "agent_decision_reviews"

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.DECISIONS].create_index("decision_id", unique=True)
        await db[self.DECISIONS].create_index("task_id")
        await db[self.DECISIONS].create_index("business_id")
        await db[self.DECISIONS].create_index("session_id")
        await db[self.DECISIONS].create_index([("task_id", 1), ("sequence", 1)])
        await db[self.EXPLANATIONS].create_index("explanation_id", unique=True)
        await db[self.EXPLANATIONS].create_index("task_id")
        await db[self.VALIDATIONS].create_index("validation_id", unique=True)
        await db[self.VALIDATIONS].create_index("task_id")
        await db[self.REVIEWS].create_index("review_id", unique=True)
        await db[self.REVIEWS].create_index("task_id")
        await db[self.REVIEWS].create_index("status")
        self._initialized = True

    async def save_decision_record(self, record: DecisionRecordDoc) -> Dict[str, Any]:
        db = get_mongo_db()
        doc = record.model_dump(by_alias=True, exclude={"id"})
        await db[self.DECISIONS].update_one(
            {"decision_id": record.decision_id},
            {"$set": doc, "$setOnInsert": {"created_at": record.created_at}},
            upsert=True,
        )
        return doc

    async def save_explanation(
        self, explanation: LayeredExplanation
    ) -> Dict[str, Any]:
        db = get_mongo_db()
        doc = explanation.model_dump(by_alias=True, exclude={"id"})
        await db[self.EXPLANATIONS].update_one(
            {"explanation_id": explanation.explanation_id},
            {"$set": doc},
            upsert=True,
        )
        return doc

    async def save_validation(
        self, validation: ExplanationValidation
    ) -> Dict[str, Any]:
        db = get_mongo_db()
        doc = validation.model_dump(by_alias=True, exclude={"id"})
        await db[self.VALIDATIONS].update_one(
            {"validation_id": validation.validation_id},
            {"$set": doc},
            upsert=True,
        )
        return doc

    async def create_review(
        self,
        *,
        business_id: Optional[str],
        task_id: Optional[str],
        session_id: Optional[str],
        decision_id: Optional[str],
        action: str,
        reason: str,
        reviewer: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = get_mongo_db()
        review = DecisionReview(
            review_id=f"rev_{uuid.uuid4().hex[:12]}",
            business_id=business_id,
            task_id=task_id,
            session_id=session_id,
            decision_id=decision_id,
            status=ReviewStatus.PENDING,
            reviewer=reviewer,
            action=action,
            reason=reason,
            created_at=now_tz(),
            updated_at=now_tz(),
        )
        doc = review.model_dump(by_alias=True, exclude={"id"})
        await db[self.REVIEWS].insert_one(doc)
        return doc

    async def list_decision_records(
        self,
        *,
        business_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if business_id:
            query["business_id"] = business_id
        if task_id:
            query["task_id"] = task_id
        if session_id:
            query["session_id"] = session_id
        if user_id:
            query["user_id"] = user_id
        cursor = get_mongo_db()[self.DECISIONS].find(query).sort("created_at", 1).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def get_decision_record(self, decision_id: str) -> Optional[Dict[str, Any]]:
        doc = await get_mongo_db()[self.DECISIONS].find_one({"decision_id": decision_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def list_explanations(
        self,
        *,
        task_id: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if task_id:
            query["task_id"] = task_id
        if decision_id:
            query["decision_id"] = decision_id
        cursor = get_mongo_db()[self.EXPLANATIONS].find(query).sort("created_at", 1).limit(200)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def list_validations(
        self,
        *,
        task_id: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if task_id:
            query["task_id"] = task_id
        if decision_id:
            query["decision_id"] = decision_id
        cursor = get_mongo_db()[self.VALIDATIONS].find(query).sort("created_at", 1).limit(200)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def list_reviews(
        self,
        *,
        task_id: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if task_id:
            query["task_id"] = task_id
        if decision_id:
            query["decision_id"] = decision_id
        cursor = get_mongo_db()[self.REVIEWS].find(query).sort("created_at", 1).limit(200)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results


decision_record_store = DecisionRecordStore()
