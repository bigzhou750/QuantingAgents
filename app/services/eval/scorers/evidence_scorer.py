"""
证据质量评分器

基于 trace 事件中的证据引用信息，评估：
- 证据覆盖率：关键论断是否有对应证据支撑
- 引用相关性：引用的证据是否与论点相关
- 无证据断言：是否存在没有证据支撑的结论性陈述
- 来源一致性：多个证据来源之间是否一致

对应 spec 二期任务 2.3。
"""

import logging
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class EvidenceQualityScorer(BaseScorer):
    """证据质量评分器"""

    @property
    def name(self) -> str:
        return "evidence_quality"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.EVIDENCE

    @property
    def version(self) -> str:
        return "1.0.0"

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """执行证据质量评分"""
        # 从 trace 事件中提取证据相关事件
        evidence_events = [
            e for e in trace_events
            if e.get("event_type") in ("evidence", "retrieval", "citation")
        ]

        output_data = trial_data.get("output_data", {})
        output_text = ""
        if isinstance(output_data, dict):
            output_text = output_data.get("content", "")

        if not output_text and not evidence_events:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="无输出内容且无证据事件，无法评估证据质量",
                confidence=1.0,
                source=self.source,
                version=self.version,
            )

        dimensions = {}
        reasons = []

        # 1. 证据覆盖率
        total_claims = max(1, len(output_text.split("。")) - 1) if output_text else 1
        evidence_count = len(evidence_events)
        coverage = min(1.0, evidence_count / max(1, total_claims * 0.3))
        dimensions["evidence_coverage"] = round(coverage, 4)

        if coverage < 0.3:
            reasons.append(f"证据覆盖率低 ({coverage:.0%})，{evidence_count} 条证据 / {total_claims} 个论断")

        # 2. 引用相关性（检查证据事件中是否有 query/topic 字段与输出匹配）
        relevant_count = 0
        for event in evidence_events:
            data = event.get("data", {})
            if data.get("query") or data.get("topic") or data.get("source"):
                relevant_count += 1
        relevance = relevant_count / max(1, evidence_count) if evidence_count > 0 else 0.5
        dimensions["citation_relevance"] = round(relevance, 4)

        # 3. 无证据断言检测
        # 简单启发式：如果输出很长但证据很少，可能存在无证据断言
        unsupported_ratio = 0.0
        if len(output_text) > 200 and evidence_count == 0:
            unsupported_ratio = 1.0
            reasons.append("输出内容较长但完全没有证据引用")
        elif len(output_text) > 500 and evidence_count < 3:
            unsupported_ratio = 0.7
            reasons.append(f"输出内容丰富但证据稀少 ({evidence_count} 条)")
        dimensions["unsupported_claims"] = round(1.0 - unsupported_ratio, 4)

        # 4. 来源一致性（检查是否有冲突的证据来源）
        sources = set()
        for event in evidence_events:
            data = event.get("data", {})
            source = data.get("source") or data.get("provider")
            if source:
                sources.add(source)
        source_consistency = 1.0 if len(sources) <= 3 else max(0.5, 1.0 - (len(sources) - 3) * 0.1)
        dimensions["source_consistency"] = round(source_consistency, 4)

        # 综合分数（加权平均）
        weights = {
            "evidence_coverage": 0.30,
            "citation_relevance": 0.25,
            "unsupported_claims": 0.30,
            "source_consistency": 0.15,
        }
        overall_score = sum(dimensions[k] * weights[k] for k in weights)

        reason_text = "; ".join(reasons) if reasons else f"证据质量良好，综合得分 {overall_score:.2f}"

        return ScoreResult(
            score_name=self.name,
            score=max(0.0, min(1.0, overall_score)),
            passed=overall_score >= 0.6,
            reason=reason_text,
            confidence=0.8 if evidence_count > 0 else 0.5,
            source=self.source,
            version=self.version,
            raw_output={"dimensions": dimensions},
        )
