"""Claim 抽取流水线回归测试。"""

import pytest

from app.models.eval import ClaimVerdict
from app.services.eval.claim_extraction import ClaimExtractionResult, extract_claims
from app.services.eval.claim_extraction.pipeline import (
    _needs_continuation,
    normalize_text,
)


def test_normalize_text_handles_crlf_unicode_and_collapsed_whitespace():
    normalized, source_map = normalize_text("贵州茅台\r\n\n（EPS）\u3000为\t65")
    assert "\r" not in normalized
    assert "\t" not in normalized
    assert source_map
    assert len(source_map) == len(normalized)


def test_cross_line_stock_code_is_merged_into_complete_claim():
    output = (
        "贵州茅台（股票代码：600519\n"
        "SH）是中国知名的高端白酒品牌。"
    )
    result = extract_claims(output)
    assert result.claims
    assert "600519 SH" in result.claims[0].claim_text
    assert result.claims[0].source_start == 0
    assert result.claims[0].source_end is not None


def test_ambiguous_numeric_split_is_kept_with_low_priority():
    output = (
        "2025 年净利润为 823 亿元。\n"
        "2025 年每股收益（EPS）为 65\n"
        "66 元，2024 年为 68 元"
    )
    result = extract_claims(output)
    assert result.claims[0].claim_text == "2025 年净利润为 823 亿元。"
    ambiguous = [claim for claim in result.claims if "65 66 元" in claim.claim_text]
    assert ambiguous
    assert _needs_continuation("为 65", "66 元")


def test_markdown_headers_and_field_labels_are_excluded():
    output = (
        "### 基本面分析\n"
        "- **盈利能力**：\n"
        "- 2025 年净利润为 823 亿元。\n"
    )
    result = extract_claims(output)
    assert [claim.claim_text for claim in result.claims] == ["2025 年净利润为 823 亿元。"]
    reasons = {item.reason for item in result.excluded}
    assert "markdown_heading" in reasons
    assert "format_fragment" in reasons


def test_table_header_separator_and_code_block_are_excluded():
    output = (
        "| 指标 | 数值 |\n"
        "| --- | --- |\n"
        "```python\n"
        "print(1)\n"
        "```\n"
        "2025 年净利润为 823 亿元。\n"
    )
    result = extract_claims(output)
    reasons = {item.reason for item in result.excluded}
    assert "table_header" in reasons
    assert "table_separator" in reasons
    assert "code_fence" in reasons
    assert "code_block" in reasons
    assert any("2025 年净利润为 823 亿元" in claim.claim_text for claim in result.claims)


def test_cap_is_applied_after_cleaning_and_returns_truncation_stats():
    output = "### 基本面分析\n" + "2025 年净利润为 823 亿元。" * 25
    result = extract_claims(output)
    assert result.claim_count == 20
    assert result.claim_truncated is True
    assert result.claim_truncated_count == 5
    assert result.claim_truncated_at is not None
    assert result.candidate_count == 26


def test_excluded_fragments_are_not_claims():
    result = extract_claims("### 标题\n- **标签**：\n2025 年净利润为 823 亿元。")
    assert len(result.claims) == 1
    assert len(result.excluded) == 2
    assert result.to_raw_output()["claim_count"] == 1


@pytest.mark.asyncio
async def test_evidence_scorer_uses_clean_claim_count_in_metrics():
    from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer

    scorer = EvidenceQualityScorer()
    result = await scorer.score(
        {
            "output_data": {
                "content": "### 基本面分析\n- **盈利能力**：\n2025 年净利润为 823 亿元。"
            }
        },
        [
            {
                "event_type": "evidence",
                "event_id": "evt_1",
                "data": {
                    "snippet": "2025 年净利润为 823 亿元",
                    "source": "annual_report",
                },
            }
        ],
    )
    assert len(result.claims) == 1
    assert result.claims[0].verdict == ClaimVerdict.SUPPORTED
    assert result.raw_output["claim_candidate_count"] == 3
    assert result.raw_output["claim_count"] == 1
    assert result.raw_output["excluded_fragments"]
