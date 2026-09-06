"""
Bad Case 池服务

管理失败样本的收集、去重、标注、复核和按语义回流为正式评测用例。
支持从失败 trial、人工复核、安全拦截、用户反馈和线上自动采样等来源回流。
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.eval import (
    BadCaseSource,
    BadCaseSourceContext,
    DetectionSignal,
    DetectionStatus,
    EvalBadCase,
    FailureFamily,
    ReviewStatus,
)
from app.services.eval.badcase_fingerprint import compute_dedup_key
from app.services.eval.observability_adapter import redact_sensitive_data, truncate_large_text
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


def _sanitize_text(text: str, max_length: int) -> str:
    redacted = redact_sensitive_data(str(text or ""))
    return str(truncate_large_text(redacted, max_length).get("content", redacted))


def _sanitize_payload(value: Any, max_length: int) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_payload(item, max_length) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item, max_length) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value, max_length)
    return value


def _parse_signal(value: Any) -> Optional[DetectionSignal]:
    if isinstance(value, DetectionSignal):
        return value
    if isinstance(value, dict):
        try:
            return DetectionSignal(**value)
        except Exception as exc:
            logger.warning("Failed to parse detection signal: %s", exc)
    return None


class BadCaseService:
    """Bad Case 池服务"""

    COLLECTION = "eval_bad_cases"

    def __init__(self):
        self._initialized = False

    @staticmethod
    def _normalize_legacy_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        """为旧记录补充只读默认值，避免前端把手工样本误显示为待复核。"""
        doc.setdefault("detection_status", DetectionStatus.CONFIRMED.value)
        doc.setdefault("review_status", ReviewStatus.MANUAL.value)
        doc.setdefault("detection_signals", [])
        doc.setdefault("detection_confidence", 0.0)
        doc.setdefault("review_required", False)
        doc.setdefault("reflow_status", "converted" if doc.get("converted_to_case_id") else "pending")
        doc.setdefault("occurrence_count", 1)
        doc.setdefault("affected_versions", [])
        return doc

    async def initialize(self):
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("bad_case_id", unique=True)
        await db[self.COLLECTION].create_index("source")
        await db[self.COLLECTION].create_index("risk_level")
        await db[self.COLLECTION].create_index("created_at")
        await db[self.COLLECTION].create_index("dedup_key", unique=True, sparse=True)
        await db[self.COLLECTION].create_index("detection_status")
        await db[self.COLLECTION].create_index("review_status")
        self._initialized = True

    async def create_bad_case(
        self,
        source: str,
        input_data: Dict[str, Any],
        output_data: Optional[Dict[str, Any]] = None,
        failure_reason: str = "",
        risk_level: str = "medium",
        tags: Optional[List[str]] = None,
        source_trial_id: Optional[str] = None,
        source_run_id: Optional[str] = None,
        created_by: str = "",
        source_trace_id: Optional[str] = None,
        business_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        decision_chain_ref: Optional[str] = None,
        explanation_status: Optional[str] = None,
        release_receipt_id: Optional[str] = None,
        artifact_version: Optional[str] = None,
        failure_family: Optional[str] = None,
        detection_signals: Optional[List[Any]] = None,
        detection_confidence: float = 0.0,
        detection_status: str = DetectionStatus.CONFIRMED.value,
        review_status: str = ReviewStatus.MANUAL.value,
        review_required: bool = False,
        dedup_key: Optional[str] = None,
        source_context: Optional[Any] = None,
        reflow_status: str = "pending",
        occurrence_count: int = 1,
        affected_versions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """创建 Bad Case"""
        db = get_mongo_db()
        max_length = settings.ONLINE_BADCASE_MAX_CONTENT_LENGTH
        safe_input = _sanitize_payload(input_data, max_length)
        safe_output = _sanitize_payload(output_data, max_length) if output_data else None

        parsed_signals = []
        for signal in detection_signals or []:
            parsed = _parse_signal(signal)
            if parsed:
                parsed_signals.append(parsed)

        parsed_context = None
        if source_context:
            if isinstance(source_context, BadCaseSourceContext):
                parsed_context = source_context
            elif isinstance(source_context, dict):
                try:
                    parsed_context = BadCaseSourceContext(**source_context)
                except Exception as exc:
                    logger.warning("Failed to parse source context: %s", exc)

        bad_case_id = f"bc_{uuid.uuid4().hex[:12]}"
        doc = EvalBadCase(
            bad_case_id=bad_case_id,
            business_id=business_id,
            task_id=task_id,
            session_id=session_id,
            decision_chain_ref=decision_chain_ref,
            explanation_status=explanation_status,
            source=BadCaseSource(source),
            source_trial_id=source_trial_id,
            source_run_id=source_run_id,
            input_data=safe_input,
            output_data=safe_output,
            failure_reason=_sanitize_text(failure_reason, max_length),
            risk_level=risk_level,
            tags=tags or [],
            created_by=created_by,
            source_trace_id=source_trace_id,
            release_receipt_id=release_receipt_id,
            artifact_version=artifact_version,
            failure_family=FailureFamily(failure_family) if failure_family else None,
            detection_signals=parsed_signals,
            detection_confidence=detection_confidence,
            detection_status=DetectionStatus(detection_status),
            review_status=ReviewStatus(review_status),
            review_required=review_required,
            dedup_key=dedup_key,
            source_context=parsed_context,
            reflow_status=reflow_status,
            occurrence_count=max(1, int(occurrence_count)),
            affected_versions=affected_versions or ([] if not artifact_version else [artifact_version]),
        )

        await db[self.COLLECTION].insert_one(doc.model_dump(by_alias=True, exclude={"id"}))
        logger.info("Created bad case %s from %s", bad_case_id, source)
        return {"bad_case_id": bad_case_id}

    async def create_online_bad_case(
        self,
        source: str,
        input_data: Dict[str, Any],
        output_data: Optional[Dict[str, Any]] = None,
        failure_reason: str = "",
        risk_level: str = "medium",
        failure_family: Optional[str] = None,
        detection_signals: Optional[List[Any]] = None,
        detection_confidence: float = 0.0,
        detection_status: str = DetectionStatus.CONFIRMED.value,
        review_status: str = ReviewStatus.PENDING.value,
        review_required: bool = True,
        dedup_key: Optional[str] = None,
        source_context: Optional[Any] = None,
        artifact_version: Optional[str] = None,
        release_receipt_id: Optional[str] = None,
        business_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        decision_chain_ref: Optional[str] = None,
        explanation_status: Optional[str] = None,
        created_by: str = "system",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """创建或合并自动发现的线上 Bad Case。"""
        db = get_mongo_db()
        family = failure_family or FailureFamily.EXECUTION.value
        signal_types = []
        for signal in detection_signals or []:
            parsed = _parse_signal(signal)
            if parsed:
                signal_types.append(parsed.signal_type)
        if not dedup_key:
            dedup_key = compute_dedup_key(
                input_data=input_data,
                failure_family=family,
                failure_reason=failure_reason,
                artifact_version=artifact_version,
                data_window=getattr(source_context, "data_window", None)
                if isinstance(source_context, BadCaseSourceContext)
                else (source_context or {}).get("data_window") if isinstance(source_context, dict) else None,
                signal_types=signal_types,
            )

        existing = await db[self.COLLECTION].find_one({"dedup_key": dedup_key}) if dedup_key else None
        if existing:
            return await self._merge_existing_bad_case(
                existing=existing,
                failure_reason=failure_reason,
                risk_level=risk_level,
                detection_signals=detection_signals or [],
                detection_status=detection_status,
                review_status=review_status,
                artifact_version=artifact_version,
                tags=tags or [],
            )

        return await self.create_bad_case(
            source=source,
            input_data=input_data,
            output_data=output_data,
            failure_reason=failure_reason,
            risk_level=risk_level,
            business_id=business_id,
            task_id=task_id,
            session_id=session_id,
            decision_chain_ref=decision_chain_ref,
            explanation_status=explanation_status,
            tags=tags or [],
            created_by=created_by,
            release_receipt_id=release_receipt_id,
            artifact_version=artifact_version,
            failure_family=family,
            detection_signals=detection_signals,
            detection_confidence=detection_confidence,
            detection_status=detection_status,
            review_status=review_status,
            review_required=review_required,
            dedup_key=dedup_key,
            source_context=source_context,
        )

    async def _merge_existing_bad_case(
        self,
        existing: Dict[str, Any],
        failure_reason: str,
        risk_level: str,
        detection_signals: List[Any],
        detection_status: str,
        review_status: str,
        artifact_version: Optional[str],
        tags: List[str],
    ) -> Dict[str, Any]:
        bad_case_id = existing.get("bad_case_id", "")
        merged_signals = list(existing.get("detection_signals") or [])
        for signal in detection_signals:
            parsed = _parse_signal(signal)
            if not parsed:
                continue
            signal_doc = parsed.model_dump()
            key = (signal_doc.get("signal_type"), signal_doc.get("detector_version"))
            if not any(
                (item.get("signal_type"), item.get("detector_version")) == key
                for item in merged_signals
                if isinstance(item, dict)
            ):
                merged_signals.append(signal_doc)

        update = {
            "$inc": {"occurrence_count": 1},
            "$set": {
                "updated_at": now_tz(),
                "failure_reason": _sanitize_text(failure_reason or existing.get("failure_reason", ""), settings.ONLINE_BADCASE_MAX_CONTENT_LENGTH),
                "risk_level": risk_level or existing.get("risk_level", "medium"),
                "detection_signals": merged_signals,
                "detection_status": DetectionStatus(detection_status).value,
                "review_status": ReviewStatus(review_status).value,
                "tags": list(set(list(existing.get("tags") or []) + list(tags))),
            },
        }
        if artifact_version:
            update["$addToSet"] = {"affected_versions": artifact_version}

        db = get_mongo_db()
        await db[self.COLLECTION].update_one({"bad_case_id": bad_case_id}, update)
        logger.info("Merged duplicate online bad case %s (dedup_key=%s)", bad_case_id, existing.get("dedup_key"))
        return {"bad_case_id": bad_case_id, "deduplicated": True}

    async def create_from_failed_trial(
        self,
        trial_id: str,
        created_by: str = "",
    ) -> Optional[Dict[str, Any]]:
        """从失败的 trial 自动创建 bad case"""
        db = get_mongo_db()
        trial = await db["eval_trials"].find_one({"trial_id": trial_id})
        if not trial:
            return None

        return await self.create_bad_case(
            source=BadCaseSource.TRIAL_FAILURE.value,
            input_data=trial.get("input_data", {}),
            output_data=trial.get("output_data"),
            failure_reason=trial.get("error_message", "Trial failed"),
            risk_level="medium",
            source_trial_id=trial_id,
            source_run_id=trial.get("run_id"),
            created_by=created_by,
            failure_family=FailureFamily.EXECUTION.value,
            detection_status=DetectionStatus.CONFIRMED.value,
            review_status=ReviewStatus.MANUAL.value,
        )

    async def list_bad_cases(
        self,
        source: Optional[str] = None,
        risk_level: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        detection_status: Optional[str] = None,
        review_status: Optional[str] = None,
        failure_family: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出 bad cases"""
        db = get_mongo_db()

        query = {}
        if source:
            query["source"] = source
        if risk_level:
            query["risk_level"] = risk_level
        if detection_status:
            query["detection_status"] = detection_status
        if review_status:
            query["review_status"] = review_status
        if failure_family:
            query["failure_family"] = failure_family

        cursor = db[self.COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            object_id = doc.pop("_id", None)
            if object_id is not None:
                doc["id"] = str(object_id)
            results.append(self._normalize_legacy_doc(doc))
        return results

    async def list_review_queue(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """列出待人工复核的 Bad Case。"""
        return await self.list_bad_cases(
            detection_status=DetectionStatus.CANDIDATE.value,
            review_status=ReviewStatus.PENDING.value,
            skip=skip,
            limit=limit,
        )

    async def get_bad_case(self, bad_case_id: str) -> Optional[Dict[str, Any]]:
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one({"bad_case_id": bad_case_id})
        if doc:
            object_id = doc.pop("_id", None)
            if object_id is not None:
                doc["id"] = str(object_id)
            doc = self._normalize_legacy_doc(doc)
        return doc

    async def review_bad_case(
        self,
        bad_case_id: str,
        action: str,
        reviewer: str,
        comment: str = "",
        failure_family: Optional[str] = None,
        tags: Optional[List[str]] = None,
        label_version: Optional[str] = None,
        truth_label: Optional[str] = None,
        hallucination_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """人工复核 Bad Case，approve 或 reject。"""
        db = get_mongo_db()
        bad_case = await self.get_bad_case(bad_case_id)
        if not bad_case:
            return None

        if action == "approve":
            update_fields = {
                "review_status": ReviewStatus.APPROVED.value,
                "detection_status": DetectionStatus.CONFIRMED.value,
                "review_required": False,
                "reviewer": reviewer,
                "review_comment": comment,
                "updated_at": now_tz(),
            }
        elif action == "reject":
            update_fields = {
                "review_status": ReviewStatus.REJECTED.value,
                "detection_status": DetectionStatus.REJECTED.value,
                "review_required": False,
                "reviewer": reviewer,
                "review_comment": comment,
                "updated_at": now_tz(),
            }
        else:
            raise ValueError("Review action must be approve or reject")

        if failure_family:
            update_fields["failure_family"] = FailureFamily(failure_family).value
        if tags is not None:
            update_fields["tags"] = tags
        if label_version:
            update_fields["label_version"] = label_version
        if truth_label:
            update_fields["truth_label"] = truth_label
        if hallucination_type:
            update_fields["hallucination_type"] = hallucination_type

        await db[self.COLLECTION].update_one(
            {"bad_case_id": bad_case_id},
            {"$set": update_fields},
        )
        return await self.get_bad_case(bad_case_id)

    async def convert_to_case(
        self,
        bad_case_id: str,
        dataset_id: str,
        created_by: str = "",
    ) -> Optional[Dict[str, Any]]:
        """兼容旧入口：按新回流语义转换 Bad Case。"""
        return await self.reflow_with_policy(
            bad_case_id=bad_case_id,
            dataset_id=dataset_id,
            created_by=created_by,
        )

    async def reflow_with_policy(
        self,
        bad_case_id: str,
        dataset_id: str,
        created_by: str = "",
        expected_output: Optional[Dict[str, Any]] = None,
        truth_label: Optional[str] = None,
        hallucination_type: Optional[str] = None,
        label_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """按失败家族和复核状态将 Bad Case 回流为语义正确的评测样本。"""
        from app.services.eval.dataset_service import dataset_service

        bad_case = await self.get_bad_case(bad_case_id)
        if not bad_case:
            return None

        family = str(bad_case.get("failure_family") or FailureFamily.EXECUTION.value)
        truth_label = truth_label or bad_case.get("truth_label")
        hallucination_type = hallucination_type or bad_case.get("hallucination_type")
        label_version = label_version or bad_case.get("label_version")
        review_status = str(bad_case.get("review_status") or ReviewStatus.MANUAL.value)
        detection_status = str(bad_case.get("detection_status") or DetectionStatus.CONFIRMED.value)
        review_required = bool(bad_case.get("review_required"))
        reason = str(bad_case.get("failure_reason") or "")

        if detection_status == DetectionStatus.REJECTED.value or review_status == ReviewStatus.REJECTED.value:
            raise ValueError("Rejected Bad Case cannot be reflowed")

        purpose = self._purpose_for_reflow(
            family=family,
            review_status=review_status,
            expected_output=expected_output,
        )
        if purpose == "golden" and (review_status in (ReviewStatus.PENDING.value, ReviewStatus.AUTO_CONFIRMED.value)):
            raise ValueError("Golden Set reflow requires human approval")
        scoring_criteria, case_name = self._build_reflow_criteria(
            family=family,
            reason=reason,
            expected_output=expected_output,
        )
        tags = [
            "bad_case_reflow",
            f"failure_family:{family}",
            f"purpose:{purpose}",
        ]
        metadata = {
            "source_bad_case_id": bad_case_id,
            "source_context": bad_case.get("source_context"),
            "detection_signals": bad_case.get("detection_signals") or [],
            "dataset_purpose": purpose,
            "reflow_at": now_tz().isoformat(),
            "reflowed_by": created_by or "system",
            "replayable": bool((bad_case.get("source_context") or {}).get("replayable", False))
            if isinstance(bad_case.get("source_context"), dict)
            else True,
            "truth_label": truth_label,
            "hallucination_type": hallucination_type,
            "label_version": label_version,
        }

        result = await dataset_service.add_case(
            dataset_id=dataset_id,
            name=case_name,
            input_data=bad_case.get("input_data", {}),
            expected_output=expected_output,
            scoring_criteria=scoring_criteria,
            tags=tags,
            description=f"From bad case {bad_case_id}, family={family}, source={bad_case.get('source')}",
            category="regression" if purpose == "online_regression" else "general",
            metadata=metadata,
        )

        db = get_mongo_db()
        await db[self.COLLECTION].update_one(
            {"bad_case_id": bad_case_id},
            {
                "$set": {
                    "converted_to_case_id": result.get("case_id"),
                    "reflow_status": "converted",
                    "reflow_metadata": metadata,
                    "updated_at": now_tz(),
                }
            },
        )
        logger.info("Reflowed bad case %s to case %s (%s)", bad_case_id, result.get("case_id"), purpose)
        return {**result, "reflow_metadata": metadata}

    @staticmethod
    def _purpose_for_reflow(
        family: str,
        review_status: str,
        expected_output: Optional[Dict[str, Any]],
    ) -> str:
        if family in (FailureFamily.EXECUTION.value, FailureFamily.TOOL_TRAJECTORY.value):
            return "online_regression"
        if family == FailureFamily.SAFETY_COMPLIANCE.value:
            return "golden" if review_status in (ReviewStatus.APPROVED.value, ReviewStatus.MANUAL.value) else "review_queue"
        if family == FailureFamily.EVIDENCE_HALLUCINATION.value:
            return "detector_eval" if review_status in (ReviewStatus.APPROVED.value, ReviewStatus.MANUAL.value) else "review_queue"
        if family == FailureFamily.USER_FEEDBACK.value:
            return "golden" if expected_output else "review_queue"
        return "review_queue"

    @staticmethod
    def _build_reflow_criteria(
        family: str,
        reason: str,
        expected_output: Optional[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str]:
        lowered = reason.lower()
        if family in (FailureFamily.EXECUTION.value, FailureFamily.TOOL_TRAJECTORY.value):
            criteria = {
                "must_complete": True,
                "must_have_final_report": True,
                "must_not_timeout": "timeout" in lowered or "超时" in reason,
                "must_not_contain_reason": reason[:200],
            }
            if "permission" in lowered or "权限" in reason:
                criteria["must_not_have_permission_violation"] = True
            return criteria, f"[BadCase:Execution] {reason[:60]}"
        if family == FailureFamily.SAFETY_COMPLIANCE.value:
            return {
                "must_not_have_safety_risk": True,
                "must_not_repeat_reason": reason[:200],
            }, f"[BadCase:Safety] {reason[:60]}"
        if family == FailureFamily.EVIDENCE_HALLUCINATION.value:
            return {
                "min_evidence_coverage": 0.8,
                "max_unsupported_ratio": 0.1,
                "max_contradiction_ratio": 0.0,
                "must_include_data_time_range": True,
                "must_not_repeat_claim_error": reason[:200],
            }, f"[BadCase:Evidence] {reason[:60]}"
        if family == FailureFamily.USER_FEEDBACK.value:
            return {
                "must_address_user_feedback": True,
                "must_not_repeat_feedback": reason[:200],
            }, f"[BadCase:Feedback] {reason[:60]}"
        if expected_output:
            return {"must_match_curated_output": True}, f"[BadCase:Curated] {reason[:60]}"
        return {"must_not_repeat_reason": reason[:200]}, f"[BadCase:Quality] {reason[:60]}"

    async def delete_bad_case(self, bad_case_id: str) -> bool:
        db = get_mongo_db()
        result = await db[self.COLLECTION].delete_one({"bad_case_id": bad_case_id})
        return result.deleted_count > 0

    async def get_stats(self) -> Dict[str, Any]:
        """获取 bad case 池统计"""
        db = get_mongo_db()

        total = await db[self.COLLECTION].count_documents({})
        by_source = {}
        async for doc in db[self.COLLECTION].aggregate([
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        ]):
            by_source[doc["_id"]] = doc["count"]

        by_risk = {}
        async for doc in db[self.COLLECTION].aggregate([
            {"$group": {"_id": "$risk_level", "count": {"$sum": 1}}},
        ]):
            by_risk[doc["_id"]] = doc["count"]

        by_detection_status = {}
        async for doc in db[self.COLLECTION].aggregate([
            {"$group": {"_id": "$detection_status", "count": {"$sum": 1}}},
        ]):
            by_detection_status[doc["_id"]] = doc["count"]

        converted = await db[self.COLLECTION].count_documents({
            "converted_to_case_id": {"$exists": True, "$ne": None}
        })

        return {
            "total": total,
            "by_source": by_source,
            "by_risk_level": by_risk,
            "by_detection_status": by_detection_status,
            "converted_count": converted,
            "pending_count": total - converted,
        }


# 单例实例
bad_case_service = BadCaseService()
