"""Claim 抽取结果的数据结构。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.eval import ClaimEvidence


@dataclass
class ExcludedFragment:
    """被排除的原始片段及原因。"""

    text: str
    reason: str
    source_start: Optional[int] = None
    source_end: Optional[int] = None


@dataclass
class ClaimExtractionResult:
    """一次 Claim 抽取的完整结果。"""

    claims: List[ClaimEvidence] = field(default_factory=list)
    candidate_count: int = 0
    claim_count: int = 0
    claim_truncated: bool = False
    claim_truncated_count: int = 0
    claim_truncated_at: Optional[int] = None
    excluded: List[ExcludedFragment] = field(default_factory=list)
    normalized_text: str = ""

    def to_raw_output(self) -> Dict[str, Any]:
        return {
            "claim_candidate_count": self.candidate_count,
            "claim_count": self.claim_count,
            "claim_truncated": self.claim_truncated,
            "claim_truncated_count": self.claim_truncated_count,
            "claim_truncated_at": self.claim_truncated_at,
            "excluded_fragments": [
                {
                    "text": item.text,
                    "reason": item.reason,
                    "source_start": item.source_start,
                    "source_end": item.source_end,
                }
                for item in self.excluded
            ],
        }
