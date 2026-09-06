"""线上 Bad Case 自动发现与回流测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.eval import (
    BadCaseSource,
    DetectionSignal,
    FailureFamily,
    EvalBadCase,
)
from app.services.eval.badcase_fingerprint import compute_dedup_key
from app.services.eval.online_badcase_service import (
    OnlineBadcaseAdjudicator,
    detect_hard_signals,
)


class FakeCollection:
    def __init__(self, doc=None):
        self.doc = doc
        self.updated = None

    async def find_one(self, *_args, **_kwargs):
        return dict(self.doc) if isinstance(self.doc, dict) else self.doc

    async def update_one(self, *_args, **kwargs):
        self.updated = kwargs.get("update") or (_args[1] if len(_args) > 1 else None)
        return type("Result", (), {"modified_count": 1})()


class FakeDB:
    def __init__(self, doc):
        self.collection = FakeCollection(doc)

    def __getitem__(self, _name):
        return self.collection


def test_legacy_bad_case_model_is_backward_compatible():
    case = EvalBadCase(
        bad_case_id="bc_legacy",
        source=BadCaseSource.ONLINE_SAMPLING,
        input_data={"prompt": "test"},
    )
    assert case.failure_family is None
    assert case.detection_signals == []
    assert case.review_status.value == "manual"


def test_dedup_key_changes_with_failure_family_and_is_stable():
    kwargs = {
        "input_data": {"prompt": "分析贵州茅台"},
        "failure_reason": "工具超时",
        "artifact_version": "1.0.0",
        "data_window": {"date": "2026-09-06"},
    }
    first = compute_dedup_key(failure_family="execution", **kwargs)
    same = compute_dedup_key(failure_family="execution", **kwargs)
    other = compute_dedup_key(failure_family="tool_trajectory", **kwargs)
    assert first == same
    assert first != other


def test_hard_failure_signals_cover_timeout_empty_and_permission():
    signals = detect_hard_signals(
        status="failed",
        output_text="",
        error_message="Agent 运行超时",
        events=[
            {"event_id": "evt_1", "event_type": "tool_result", "payload": {"permission_denied": True}},
        ],
    )
    signal_types = {signal.signal_type for signal in signals}
    assert {"runtime.failed", "runtime.timeout", "tool.permission_denied"} <= signal_types


def test_single_soft_signal_is_routed_to_review():
    decision = OnlineBadcaseAdjudicator.adjudicate(
        [
            DetectionSignal(
                signal_type="llm_judge",
                failure_family=FailureFamily.OUTPUT_QUALITY,
                score=0.3,
                confidence=0.85,
                reason="answer is incomplete",
            )
        ]
    )
    assert decision.route == "review_required"
    assert decision.review_required is True


def test_hard_failure_is_auto_confirmed():
    signals = detect_hard_signals("failed", "", "runtime error", [])
    decision = OnlineBadcaseAdjudicator.adjudicate(signals)
    assert decision.route == "auto_confirmed"
    assert decision.review_status == "auto_confirmed"
    assert decision.failure_family == "execution"


def test_safety_signal_requires_review():
    decision = OnlineBadcaseAdjudicator.adjudicate(
        [
            DetectionSignal(
                signal_type="safety",
                failure_family=FailureFamily.SAFETY_COMPLIANCE,
                score=0.2,
                confidence=0.9,
                severity="high",
                reason="sensitive data leak",
            )
        ]
    )
    assert decision.route == "review_required"
    assert decision.review_required is True
    assert decision.detection_status == "confirmed"


@pytest.mark.asyncio
async def test_duplicate_online_bad_case_is_merged():
    from app.services.eval.bad_case_service import BadCaseService

    existing = {
        "_id": "mongo-id",
        "bad_case_id": "bc_existing",
        "dedup_key": "sha256:duplicate",
        "failure_reason": "old reason",
        "risk_level": "medium",
        "detection_signals": [],
        "tags": [],
    }
    fake_db = FakeDB(existing)
    with patch("app.services.eval.bad_case_service.get_mongo_db", return_value=fake_db):
        result = await BadCaseService().create_online_bad_case(
            source="online_sampling",
            input_data={"prompt": "test"},
            failure_reason="new reason",
            failure_family="execution",
            dedup_key="sha256:duplicate",
            artifact_version="1.0.1",
        )
    assert result["bad_case_id"] == "bc_existing"
    assert result["deduplicated"] is True
    assert fake_db.collection.updated["$inc"]["occurrence_count"] == 1


@pytest.mark.asyncio
async def test_reflow_never_uses_bad_output_as_expected_output():
    bad_case = {
        "bad_case_id": "bc_reflow",
        "source": "online_sampling",
        "input_data": {"prompt": "分析股票"},
        "output_data": {"content": "这是错误答案"},
        "failure_reason": "runtime timeout",
        "failure_family": "execution",
        "detection_status": "confirmed",
        "review_status": "auto_confirmed",
        "review_required": False,
        "source_context": {"replayable": False},
        "detection_signals": [],
    }
    fake_db = FakeDB(bad_case)

    from app.services.eval.bad_case_service import BadCaseService
    from app.services.eval.dataset_service import dataset_service

    add_case = AsyncMock(return_value={
        "case_id": "case_reflow",
        "dataset_id": "ds_online",
        "dataset_version": "1.0.1",
    })
    with patch("app.services.eval.bad_case_service.get_mongo_db", return_value=fake_db), \
         patch.object(dataset_service, "add_case", add_case):
        result = await BadCaseService().reflow_with_policy("bc_reflow", "ds_online")

    kwargs = add_case.await_args.kwargs
    assert kwargs["expected_output"] is None
    assert kwargs["scoring_criteria"]["must_complete"] is True
    assert result["case_id"] == "case_reflow"
    assert fake_db.collection.updated["$set"]["reflow_status"] == "converted"
