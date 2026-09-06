from app.models.eval import ClaimEvidence, ClaimTruthLabel, HallucinationType
from app.services.eval.metrics_service import MetricsService
import pytest


def test_claim_model_accepts_truth_and_prediction_fields():
    claim = ClaimEvidence(
        claim_id="c1",
        claim_text="接口由订单服务负责",
        truth_label=ClaimTruthLabel.SUPPORTED,
        truth_source="human_review",
        hallucination_type=HallucinationType.ENTITY,
        prediction_label=False,
        label_version="1.0",
    )

    assert claim.truth_label == ClaimTruthLabel.SUPPORTED
    assert claim.prediction_label is False
    assert claim.hallucination_type == HallucinationType.ENTITY


def test_claim_annotation_requires_label_version():
    from pydantic import ValidationError
    from app.routers.eval import ClaimAnnotationRequest

    with pytest.raises(ValidationError):
        ClaimAnnotationRequest(
            score_id="s1",
            claim_id="c1",
            truth_label="supported",
            label_version="",
        )


def test_hallucination_metrics_calculate_confusion_matrix_and_scores():
    claims = [
        {"truth_label": "unsupported", "prediction_label": True, "truth_source": "r1", "label_version": "1.0"},
        {"truth_label": "contradicted", "prediction_label": False, "truth_source": "r1", "label_version": "1.0"},
        {"truth_label": "supported", "prediction_label": True, "truth_source": "r1", "label_version": "1.0"},
        {"truth_label": "supported", "prediction_label": False, "truth_source": "r1", "label_version": "1.0"},
    ]

    result = MetricsService.compute_hallucination_metrics(claims)

    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["tn"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5
    assert result["unsupported_pass_rate"] == 0.0
    assert result["contradicted_pass_rate"] == 1.0
    assert result["eligible_claims"] == 4


def test_hallucination_metrics_exclude_unlabeled_and_group_by_type():
    claims = [
        {
            "truth_label": "unsupported",
            "prediction_label": True,
            "hallucination_type": "numeric",
            "truth_source": "r1",
            "label_version": "1.0",
        },
        {
            "truth_label": "supported",
            "prediction_label": False,
            "hallucination_type": "numeric",
            "truth_source": "r1",
            "label_version": "1.0",
        },
        {"truth_label": None, "prediction_label": True, "hallucination_type": "entity"},
        {"truth_label": "excluded", "prediction_label": False, "hallucination_type": "entity"},
    ]

    result = MetricsService.compute_hallucination_metrics(claims)

    assert result["eligible_claims"] == 2
    assert result["excluded_claims"] == 2
    assert result["by_type"]["numeric"]["f1"] == 1.0
    assert "entity" not in result["by_type"]


def test_hallucination_metrics_are_not_available_without_positive_samples():
    result = MetricsService.compute_hallucination_metrics([
        {"truth_label": "supported", "prediction_label": False, "truth_source": "r1", "label_version": "1.0"},
    ])

    assert result["status"] == "available"
    assert result["recall"] is None
    assert result["f1"] is None


def test_legacy_claims_remain_excluded_from_classification_metrics():
    result = MetricsService.compute_hallucination_metrics([
        {"verdict": "unsupported"},
        {"verdict": "supported"},
    ])

    assert result["status"] == "not_available"
    assert result["eligible_claims"] == 0
    assert result["excluded_claims"] == 2


@pytest.mark.asyncio
async def test_evidence_scorer_emits_prediction_without_overwriting_verdict():
    from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer

    result = await EvidenceQualityScorer().score(
        {"output_data": {"content": "接口路径是 /api/missing/query"}},
        [],
    )

    assert result.claims
    assert result.claims[0].verdict.value == "unscorable"
    assert result.claims[0].prediction_label is None
    assert result.claims[0].prediction_reason
