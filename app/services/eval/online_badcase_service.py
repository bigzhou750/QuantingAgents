"""线上 Bad Case 自动发现服务。

该模块复用现有评分器、trace adapter 和 Bad Case 池，将线上 Vibe Agent
终态事件转换为带检测信号、置信度和去重指纹的 Bad Case 候选。
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.eval import (
    BadCaseSourceContext,
    DetectionSignal,
    DetectionStatus,
    FailureFamily,
    ReviewStatus,
)
from app.services.eval.badcase_fingerprint import (
    compute_dedup_key,
    hash_user_id,
)
from app.services.eval.online_badcase_config_service import (
    online_badcase_config_service,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


HARD_SIGNAL_TYPES = {
    "runtime.failed",
    "runtime.timeout",
    "output.empty",
    "tool.permission_denied",
}


@dataclass
class AdjudicationDecision:
    """自动判定路由结果"""

    route: str
    detection_status: str
    review_status: str
    review_required: bool
    detection_confidence: float
    failure_family: Optional[str]
    risk_level: str


def build_pseudo_trial(
    prompt: str,
    output_data: Optional[Dict[str, Any]],
    status: str,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """将线上会话转成现有评分器可接受的 trial 形状。"""
    return {
        "input_data": {"prompt": prompt or ""},
        "output_data": output_data or {"content": "", "status": status},
        "status": status,
        "error_message": error_message or "",
    }


async def build_trace_events(
    events: List[Dict[str, Any]],
    trace_id: str,
) -> List[Dict[str, Any]]:
    """将线上事件归一化为 scorer 可读取的 trace 事件。"""
    from app.services.eval.trace_adapter import trace_adapter

    docs = []
    for index, event in enumerate(events):
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"raw": payload}
        vibe_event = {
            "type": event.get("event_type") or "",
            "data": payload,
            "timestamp": event.get("created_at"),
        }
        doc = trace_adapter.adapt_vibe_event(vibe_event, trace_id, index)
        if doc:
            docs.append(doc.model_dump(by_alias=True, exclude={"id"}))
    return docs


def detect_hard_signals(
    status: str,
    output_text: str,
    error_message: Optional[str],
    events: List[Dict[str, Any]],
) -> List[DetectionSignal]:
    """识别执行、输出和权限类硬失败信号。"""
    signals: List[DetectionSignal] = []
    error_text = str(error_message or "").lower()

    if status in ("failed", "error") or "attempt.failed" in {
        event.get("event_type", "") for event in events
    }:
        signals.append(
            DetectionSignal(
                signal_type="runtime.failed",
                failure_family=FailureFamily.EXECUTION,
                score=0.0,
                confidence=1.0,
                severity="high",
                reason=error_message or "Agent runtime returned a failed status",
                detector_name="hard_failure_detector",
                detector_version="1.0.0",
            )
        )

    if "timeout" in error_text or "超时" in error_text:
        signals.append(
            DetectionSignal(
                signal_type="runtime.timeout",
                failure_family=FailureFamily.EXECUTION,
                score=0.0,
                confidence=1.0,
                severity="high",
                reason="Agent runtime timed out",
                detector_name="hard_failure_detector",
                detector_version="1.0.0",
            )
        )

    if status in ("completed", "success", "ok") and not str(output_text or "").strip():
        signals.append(
            DetectionSignal(
                signal_type="output.empty",
                failure_family=FailureFamily.EXECUTION,
                score=0.0,
                confidence=1.0,
                severity="high",
                reason="Completed task produced no final output",
                detector_name="hard_failure_detector",
                detector_version="1.0.0",
            )
        )

    permission_hits = [
        event
        for event in events
        if (event.get("payload") or {}).get("permission_denied")
        or (event.get("payload") or {}).get("access_denied")
    ]
    if permission_hits or "permission denied" in error_text or "权限" in error_text:
        signals.append(
            DetectionSignal(
                signal_type="tool.permission_denied",
                failure_family=FailureFamily.SAFETY_COMPLIANCE,
                score=0.0,
                confidence=1.0,
                severity="high",
                reason="Agent attempted an operation denied by permission policy",
                evidence_refs=[str(event.get("event_id") or "") for event in permission_hits[:5]],
                detector_name="hard_failure_detector",
                detector_version="1.0.0",
            )
        )

    tool_names = []
    for event in events:
        payload = event.get("payload") or {}
        if event.get("event_type") == "tool_call":
            tool_names.append(str(payload.get("name") or payload.get("tool") or ""))
    consecutive = 0
    max_consecutive = 0
    previous = None
    for name in tool_names:
        if name and name == previous:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
        previous = name
    if max_consecutive >= 3:
        signals.append(
            DetectionSignal(
                signal_type="trajectory.loop",
                failure_family=FailureFamily.TOOL_TRAJECTORY,
                score=0.0,
                confidence=0.95,
                severity="medium",
                reason=f"Detected {max_consecutive + 1} consecutive identical tool calls",
                detector_name="hard_failure_detector",
                detector_version="1.0.0",
            )
        )

    return signals


async def collect_soft_signals(
    pseudo_trial: Dict[str, Any],
    trace_events: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> List[DetectionSignal]:
    """复用现有 scorer 生成软质量信号，任何单个 scorer 失败都不阻断线上流程。"""
    if config is None:
        config = await online_badcase_config_service.get_effective_config()
    signals: List[DetectionSignal] = []
    scorer_configs = [
        ("output_completeness", FailureFamily.OUTPUT_QUALITY, float(config.get("judge_threshold", settings.ONLINE_BADCASE_JUDGE_THRESHOLD))),
        ("evidence_quality", FailureFamily.EVIDENCE_HALLUCINATION, float(config.get("evidence_threshold", settings.ONLINE_BADCASE_EVIDENCE_THRESHOLD))),
        ("safety", FailureFamily.SAFETY_COMPLIANCE, 0.8),
        ("trajectory", FailureFamily.TOOL_TRAJECTORY, 0.6),
    ]

    for scorer_name, family, threshold in scorer_configs:
        try:
            if scorer_name == "output_completeness":
                from app.services.eval.scorers.output_scorer import OutputCompletenessScorer
                scorer = OutputCompletenessScorer()
            elif scorer_name == "evidence_quality":
                from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer
                scorer = EvidenceQualityScorer()
            elif scorer_name == "safety":
                from app.services.eval.scorers.safety_scorer import SafetyScorer
                scorer = SafetyScorer()
            else:
                from app.services.eval.scorers.trajectory_scorer import TrajectoryScorer
                scorer = TrajectoryScorer()

            result = await scorer.score(pseudo_trial, trace_events, {})
            if not result.passed or result.score < threshold:
                severity = result.raw_output.get("risk_level", "medium") if isinstance(result.raw_output, dict) else "medium"
                signals.append(
                    DetectionSignal(
                        signal_type=result.score_name,
                        failure_family=family,
                        score=result.score,
                        confidence=result.confidence,
                        severity=str(severity),
                        reason=result.reason,
                        evidence_refs=result.evidence_refs,
                        detector_name=result.score_name,
                        detector_version=result.version,
                    )
                )
        except Exception as exc:
            logger.warning("[OnlineBadcase] scorer %s failed: %s", scorer_name, exc)

    if config.get("enable_judge") and (settings.EVAL_JUDGE_MODEL or settings.EVAL_JUDGE_MODEL_DEFAULT):
        try:
            from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer

            judge = LLMJudgeScorer(
                judge_model=settings.EVAL_JUDGE_MODEL or settings.EVAL_JUDGE_MODEL_DEFAULT
            )
            result = await judge.score(pseudo_trial, trace_events, {})
            if result.confidence > 0 and (
                not result.passed
                or result.score < float(config.get("judge_threshold", settings.ONLINE_BADCASE_JUDGE_THRESHOLD))
            ):
                signals.append(
                    DetectionSignal(
                        signal_type=result.score_name,
                        failure_family=FailureFamily.OUTPUT_QUALITY,
                        score=result.score,
                        confidence=result.confidence,
                        severity="medium",
                        reason=result.reason,
                        detector_name=result.score_name,
                        detector_version=result.version,
                    )
                )
        except Exception as exc:
            logger.warning("[OnlineBadcase] LLM judge failed: %s", exc)

    return signals


class OnlineBadcaseAdjudicator:
    """将信号列表转换为自动路由决策。"""

    @staticmethod
    def adjudicate(
        signals: List[DetectionSignal],
        user_feedback: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AdjudicationDecision:
        hard_signals = [signal for signal in signals if signal.signal_type in HARD_SIGNAL_TYPES]
        safety_signals = [
            signal
            for signal in signals
            if signal.failure_family == FailureFamily.SAFETY_COMPLIANCE
        ]
        failed_soft = [
            signal
            for signal in signals
            if signal.signal_type not in HARD_SIGNAL_TYPES
            and (signal.score < 0.6 or signal.confidence < 0.5)
        ]

        family = None
        for signal in signals:
            if signal.failure_family:
                family = signal.failure_family.value
                break
        if user_feedback:
            family = FailureFamily.USER_FEEDBACK.value

        severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        risk_level = "low"
        max_confidence = 0.0
        for signal in signals:
            if severity_rank.get(signal.severity, 0) > severity_rank.get(risk_level, 0):
                risk_level = signal.severity
            max_confidence = max(max_confidence, signal.confidence)

        if hard_signals:
            return AdjudicationDecision(
                route="auto_confirmed",
                detection_status=DetectionStatus.CONFIRMED.value,
                review_status=ReviewStatus.AUTO_CONFIRMED.value,
                review_required=False,
                detection_confidence=max(max_confidence, 1.0),
                failure_family=family,
                risk_level=risk_level,
            )

        if safety_signals:
            return AdjudicationDecision(
                route="review_required",
                detection_status=DetectionStatus.CONFIRMED.value,
                review_status=ReviewStatus.PENDING.value,
                review_required=True,
                detection_confidence=max_confidence,
                failure_family=family,
                risk_level=risk_level,
            )

        if user_feedback:
            return AdjudicationDecision(
                route="review_required",
                detection_status=DetectionStatus.CANDIDATE.value,
                review_status=ReviewStatus.PENDING.value,
                review_required=True,
                detection_confidence=max(max_confidence, 0.7),
                failure_family=family,
                risk_level=risk_level,
            )

        confidence_threshold = float(
            (config or {}).get(
                "confidence_threshold",
                settings.ONLINE_BADCASE_CONFIDENCE_THRESHOLD,
            )
        )
        if len(failed_soft) >= 2 and max_confidence >= confidence_threshold:
            return AdjudicationDecision(
                route="auto_confirmed",
                detection_status=DetectionStatus.CONFIRMED.value,
                review_status=ReviewStatus.AUTO_CONFIRMED.value,
                review_required=False,
                detection_confidence=max_confidence,
                failure_family=family,
                risk_level=risk_level,
            )

        if failed_soft:
            return AdjudicationDecision(
                route="review_required",
                detection_status=DetectionStatus.CANDIDATE.value,
                review_status=ReviewStatus.PENDING.value,
                review_required=True,
                detection_confidence=max_confidence,
                failure_family=family,
                risk_level=risk_level,
            )

        return AdjudicationDecision(
            route="metric_only",
            detection_status=DetectionStatus.CANDIDATE.value,
            review_status=ReviewStatus.PENDING.value,
            review_required=False,
            detection_confidence=0.0,
            failure_family=family,
            risk_level="low",
        )


class OnlineBadcaseCollector:
    """从线上终态事件采集 Bad Case。"""

    TERMINAL_EVENT_TYPES = {
        "attempt.failed",
        "attempt.completed",
        "attempt.cancelled",
    }

    async def should_sample_soft(
        self,
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if config is None:
            config = await online_badcase_config_service.get_effective_config()
        if not config.get("enabled"):
            return False
        return random.random() <= float(config.get("soft_sample_rate", settings.ONLINE_BADCASE_SOFT_SAMPLE_RATE))

    async def collect_from_online_event(
        self,
        user_id: str,
        session_id: str,
        task_id: str,
        raw_type: str,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        config = await online_badcase_config_service.get_effective_config()
        if not config.get("enabled"):
            return None
        if raw_type not in self.TERMINAL_EVENT_TYPES:
            return None

        try:
            db = get_mongo_db()
            task = await db["vibe_agent_tasks"].find_one(
                {"user_id": user_id, "session_id": session_id, "task_id": task_id}
            )
            if not task:
                return None

            messages = await db["vibe_agent_messages"].find(
                {"user_id": user_id, "session_id": session_id, "task_id": task_id},
                {"_id": 0, "role": 1, "content": 1},
            ).sort("created_at", 1).to_list(length=100)
            prompt = next(
                (str(message.get("content") or "") for message in messages if message.get("role") == "user"),
                str(task.get("prompt") or ""),
            )
            output_text = next(
                (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "assistant"),
                "",
            )

            events = await db["vibe_agent_events"].find(
                {"user_id": user_id, "session_id": session_id, "task_id": task_id},
                {"_id": 0},
            ).sort("sequence", 1).to_list(length=2000)
            if not output_text:
                token_parts = []
                for event in events:
                    if event.get("event_type") != "token":
                        continue
                    payload_value = event.get("payload") or {}
                    if isinstance(payload_value, dict):
                        token_parts.append(str(payload_value.get("text") or payload_value.get("delta") or ""))
                output_text = "".join(token_parts)

            trace_events = await build_trace_events(events, f"online_{task_id}")
            status = str(task.get("status") or "failed")
            error_message = task.get("error_message") or payload.get("error")
            output_data = {"content": output_text, "status": status} if output_text else None
            pseudo_trial = build_pseudo_trial(prompt, output_data, status, error_message)

            signals = detect_hard_signals(status, output_text, error_message, events)
            if output_text and await self.should_sample_soft(config):
                signals.extend(await collect_soft_signals(pseudo_trial, trace_events, config))

            if not signals:
                return None

            decision = OnlineBadcaseAdjudicator.adjudicate(
                signals,
                user_feedback=payload.get("feedback"),
                config=config,
            )
            dedup_key = compute_dedup_key(
                input_data={"prompt": prompt},
                failure_family=decision.failure_family or FailureFamily.EXECUTION.value,
                failure_reason=error_message or decision.failure_family or "",
                artifact_version=payload.get("artifact_version"),
                data_window=payload.get("data_window"),
                signal_types=[signal.signal_type for signal in signals],
            )

            if decision.route == "metric_only":
                await db["online_badcase_metrics"].insert_one({
                    "task_id": task_id,
                    "session_id": session_id,
                    "dedup_key": dedup_key,
                    "signals": [signal.model_dump() for signal in signals],
                    "created_at": now_tz(),
                })
                return None

            from app.services.eval.bad_case_service import bad_case_service

            source_context = BadCaseSourceContext(
                user_id_hash=hash_user_id(user_id),
                business_id=task_id,
                session_id=session_id,
                task_id=task_id,
                trace_id=f"online_{task_id}",
                data_window=payload.get("data_window"),
                artifact_versions={
                    "artifact_version": payload.get("artifact_version") or "",
                },
                release_receipt_id=payload.get("release_receipt_id"),
                replayable=bool(payload.get("data_window")),
            )
            result = await bad_case_service.create_online_bad_case(
                source="online_sampling",
                input_data={"prompt": prompt},
                output_data=output_data,
                business_id=task_id,
                task_id=task_id,
                session_id=session_id,
                decision_chain_ref=f"task_{task_id}",
                failure_reason=(
                    error_message
                    or next((signal.reason for signal in signals if signal.reason), None)
                    or "Online sample flagged by automated detection"
                ),
                risk_level=decision.risk_level,
                failure_family=decision.failure_family or FailureFamily.EXECUTION.value,
                detection_signals=signals,
                detection_confidence=decision.detection_confidence,
                detection_status=decision.detection_status,
                review_status=decision.review_status,
                review_required=decision.review_required,
                dedup_key=dedup_key,
                source_context=source_context,
                artifact_version=payload.get("artifact_version"),
                release_receipt_id=payload.get("release_receipt_id"),
                created_by="system",
            )

            try:
                from app.services.evolution.trigger_service import trigger_service
                await trigger_service.on_bad_case_event(result)
            except Exception as exc:
                logger.warning("[OnlineBadcase] trigger notification failed: %s", exc)
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[OnlineBadcase] online collection failed without blocking production: %s", exc)
            return None


online_badcase_collector = OnlineBadcaseCollector()
