import json
import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.models.eval import (
    ClaimAnnotation,
    ClaimEvidence,
    ClaimTruthLabel,
    ClaimVerdict,
    ScoreSource,
    ScoreStatus,
)


class AsyncList:
    def __init__(self, items):
        self._items = items
        self._it = None

    def sort(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._it = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def test_scoring_status_and_claim_verdict_new_values():
    assert ScoreStatus.UNSCORABLE.value == "unscorable"
    assert ScoreStatus.NOT_APPLICABLE.value == "not_applicable"
    assert ClaimVerdict.UNSCORABLE.value == "unscorable"


def test_claim_annotation_model_supports_history_and_method():
    annotation = ClaimAnnotation(
        annotation_id="ann_1",
        reviewer="reviewer-a",
        truth_label=ClaimTruthLabel.UNSUPPORTED,
        evidence_refs=["evt_1"],
        label_version="1.0",
    )
    claim = ClaimEvidence(
        claim_id="c1",
        claim_text="某接口不可用",
        annotation_history=[annotation],
        verification_method="structured_numeric_check",
    )
    assert claim.annotation_history[0].reviewer == "reviewer-a"
    assert claim.verification_method == "structured_numeric_check"


@pytest.mark.asyncio
async def test_evidence_scorer_rejects_numeric_contradiction_with_shared_ngrams():
    from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer

    result = await EvidenceQualityScorer().score(
        {"output_data": {"content": "贵州茅台2025年营收500亿元。"}},
        [
            {
                "event_type": "evidence",
                "event_id": "evt_1",
                "data": {
                    "snippet": "贵州茅台2025年营收1500亿元",
                    "source": "annual_report",
                },
            }
        ],
    )

    claim = result.claims[0]
    assert claim.verdict == ClaimVerdict.CONTRADICTED
    assert claim.prediction_label is True
    assert claim.verification_method == "structured_numeric_check"
    assert claim.conflicting_evidence


@pytest.mark.asyncio
async def test_evidence_scorer_lexical_overlap_is_not_factual_support():
    from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer

    result = await EvidenceQualityScorer().score(
        {"output_data": {"content": "贵州茅台基本面稳健，长期价值突出。"}},
        [
            {
                "event_type": "evidence",
                "event_id": "evt_1",
                "data": {"snippet": "贵州茅台基本面稳健，长期价值突出。"},
            }
        ],
    )

    assert result.claims[0].verdict == ClaimVerdict.WEAKLY_SUPPORTED
    assert result.claims[0].verification_method == "lexical_only"
    assert result.claims[0].prediction_label is None


@pytest.mark.asyncio
async def test_evidence_scorer_without_evidence_is_unscorable():
    from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer

    result = await EvidenceQualityScorer().score(
        {"output_data": {"content": "这只股票未来一定上涨。"}},
        [],
    )

    assert result.status == ScoreStatus.UNSCORABLE
    assert result.confidence == 0.0
    assert result.claims[0].verdict == ClaimVerdict.UNSCORABLE
    assert result.claims[0].prediction_label is None


def test_judge_context_builder_includes_evidence_and_expected_output():
    from app.services.eval.scorers.llm_judge_scorer import JudgeContextBuilder

    context = JudgeContextBuilder.build(
        [
            {
                "event_type": "evidence",
                "event_id": "evt_1",
                "data": {"snippet": "营收 1500 亿元", "source": "财报"},
            }
        ],
        {"expected_output": {"must_include": ["营收"]}},
        {},
    )
    assert "营收 1500 亿元" in context["evidence_text"]
    assert "must_include" in context["expected_output_text"]


@pytest.mark.asyncio
async def test_llm_judge_missing_sdk_fails_closed():
    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer

    scorer = LLMJudgeScorer(judge_model="qwen-plus")
    with patch.dict(sys.modules, {"dashscope": None}):
        with pytest.raises(RuntimeError):
            await scorer._call_judge("prompt")


@pytest.mark.asyncio
async def test_llm_judge_without_context_is_unscorable():
    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer

    result = await LLMJudgeScorer().score(
        {"input_data": {"prompt": "分析"}, "output_data": {"content": "输出"}},
        [],
        {},
    )
    assert result.status == ScoreStatus.UNSCORABLE
    assert "缺少证据或参考答案" in result.reason


@pytest.mark.asyncio
async def test_scorer_hub_uses_run_scoped_judge_config():
    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer
    from app.services.eval.scorer_hub import ScorerHub

    async def fake_judge_call(self, prompt):
        return json.dumps({"dimensions": [], "overall_score": 0.8, "overall_reason": "ok"})

    hub = ScorerHub()
    hub._scorers = {"llm_judge:llm_judge": LLMJudgeScorer()}
    score_collection = MagicMock()
    score_collection.insert_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = score_collection

    with patch("app.services.eval.scorer_hub.get_mongo_db", return_value=db):
        with patch.object(LLMJudgeScorer, "_call_judge", fake_judge_call):
            with patch.object(
                LLMJudgeScorer,
                "is_available",
                new_callable=PropertyMock,
                return_value=True,
            ):
                results = await hub.score_trial(
                    "trial_1",
                    {
                        "input_data": {"prompt": "分析"},
                        "output_data": {"content": "输出"},
                    },
                    [],
                    case_config={"expected_output": {"must_include": ["营收"]}},
                    run_config={"judge_model": "qwen-max", "rubric_version": "v2"},
                )

    assert results[0]["raw_output"]["judge_model"] == "qwen-max"
    assert results[0]["raw_output"]["rubric_version"] == "v2"
    assert results[0]["raw_output"]["has_expected_output"] is True


@pytest.mark.asyncio
async def test_scorer_hub_marks_unavailable_judge_not_configured():
    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer
    from app.services.eval.scorer_hub import ScorerHub

    hub = ScorerHub()
    hub._scorers = {"llm_judge:llm_judge": LLMJudgeScorer()}
    score_collection = MagicMock()
    score_collection.insert_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = score_collection

    with patch("app.services.eval.scorer_hub.get_mongo_db", return_value=db):
        with patch.object(
            LLMJudgeScorer,
            "is_available",
            new_callable=PropertyMock,
            return_value=False,
        ):
            results = await hub.score_trial(
                "trial_1",
                {"output_data": {"content": "输出"}},
                [],
            )

    assert results[0]["status"] == ScoreStatus.NOT_CONFIGURED.value
    assert results[0]["score"] == 0.0


@pytest.mark.asyncio
async def test_expected_content_scorer_must_include():
    from app.services.eval.scorers.expected_content_scorer import ExpectedContentScorer

    result = await ExpectedContentScorer().score(
        {"output_data": {"content": "基本面稳健，风险可控。"}},
        [],
        {"expected_output": {"must_include": ["基本面", "风险"]}},
    )
    assert result.status == ScoreStatus.PASSED
    assert result.passed is True


@pytest.mark.asyncio
async def test_expected_content_scorer_missing_item_fails():
    from app.services.eval.scorers.expected_content_scorer import ExpectedContentScorer

    result = await ExpectedContentScorer().score(
        {"output_data": {"content": "基本面稳健。"}},
        [],
        {"expected_output": {"must_include": ["基本面", "风险"]}},
    )
    assert result.status == ScoreStatus.FAILED
    assert "风险" in result.reason


@pytest.mark.asyncio
async def test_expected_content_scorer_without_expected_output_is_not_applicable():
    from app.services.eval.scorers.expected_content_scorer import ExpectedContentScorer

    result = await ExpectedContentScorer().score(
        {"output_data": {"content": "任意内容"}},
        [],
        {},
    )
    assert result.status == ScoreStatus.NOT_APPLICABLE


@pytest.mark.asyncio
async def test_pass_at_k_quality_excludes_completed_but_failed_score():
    from app.services.eval.metrics_service import MetricsService

    trials = [
        {"case_id": "case_a", "trial_id": "t1", "status": "completed"},
        {"case_id": "case_b", "trial_id": "t2", "status": "completed"},
    ]
    scores = [
        {"trial_id": "t1", "status": "passed", "score": 0.8, "passed": True, "score_name": "rule_based"},
        {"trial_id": "t2", "status": "failed", "score": 0.3, "passed": False, "score_name": "rule_based"},
    ]
    trials_collection = MagicMock()
    trials_collection.find.return_value = AsyncList(trials)
    scores_collection = MagicMock()
    scores_collection.find.return_value = AsyncList(scores)
    runs_collection = MagicMock()
    runs_collection.find_one = AsyncMock(return_value={"config": {"required_scorers": ["rule_based"]}})
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: {
        "eval_trials": trials_collection,
        "eval_scores": scores_collection,
        "eval_runs": runs_collection,
    }[name]

    with patch("app.services.eval.metrics_service.get_mongo_db", return_value=db):
        quality = await MetricsService().compute_pass_at_k("run_1", k=1, mode="quality")
        execution = await MetricsService().compute_pass_at_k("run_1", k=1, mode="execution")

    assert quality["mode"] == "quality"
    assert quality["pass_at_k"] == 0.5
    assert execution["mode"] == "execution"
    assert execution["pass_at_k"] == 1.0


@pytest.mark.asyncio
async def test_dataset_list_cases_selects_latest_available_version():
    from app.services.eval.dataset_service import EvalDatasetService

    docs = [
        {"case_id": "case_1", "version": "1.0.0", "input": {"prompt": "old"}, "archived": False},
        {"case_id": "case_1", "version": "1.0.1", "input": {"prompt": "new"}, "archived": False},
        {"case_id": "case_1", "version": "1.0.2", "input": {"prompt": "deleted"}, "archived": True},
    ]
    collection = MagicMock()
    collection.find.return_value = AsyncList(docs)
    db = MagicMock()
    db.__getitem__.return_value = collection

    with patch("app.services.eval.dataset_service.get_mongo_db", return_value=db):
        old_version_cases = await EvalDatasetService().list_cases("ds_1", version="1.0.0")
        current_cases = await EvalDatasetService().list_cases("ds_1")

    assert old_version_cases[0]["input"] == {"prompt": "old"}
    assert current_cases[0]["input"] == {"prompt": "new"}


@pytest.mark.asyncio
async def test_runner_resolves_cases_from_snapshot():
    from app.services.eval.runner_service import EvalRunnerService

    run_doc = {
        "snapshot": {
            "case_contents": {
                "case_1": {"case_id": "case_1", "input": {"prompt": "locked"}, "scoring_criteria": {}}
            }
        }
    }
    with patch(
        "app.services.eval.runner_service.dataset_service.list_cases",
        new_callable=AsyncMock,
    ) as mock_list:
        cases = await EvalRunnerService._resolve_run_cases(run_doc, "ds_1", "1.0.0")
        mock_list.assert_not_awaited()

    assert cases[0]["input"] == {"prompt": "locked"}


def test_hallucination_metrics_require_annotation_metadata_and_dispute_consensus():
    from app.services.eval.metrics_service import MetricsService

    claims = [
        {
            "truth_label": "unsupported",
            "prediction_label": True,
            "truth_source": "r1",
            "label_version": "1.0",
        },
        {
            "truth_label": "supported",
            "prediction_label": False,
            "truth_source": "r1",
            "label_version": "1.0",
            "annotation_history": [
                {"truth_label": "supported"},
                {"truth_label": "contradicted"},
            ],
        },
    ]
    result = MetricsService.compute_hallucination_metrics(claims)

    assert result["eligible_claims"] == 1
    assert result["excluded_claims"] == 1
    assert result["annotation_consistency"]["disputed"] == 1
    assert result["tp"] == 1
