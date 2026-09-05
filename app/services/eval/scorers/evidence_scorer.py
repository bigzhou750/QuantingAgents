"""
证据质量评分器（升级版）

支持 claim -> evidence 的细粒度 grounding 结果。
从 Final Output 提取可验证 claim，并为每条 claim 记录证据引用、
证据片段、来源、trace event id、verdict 和 reason。

对应 spec 任务 5.1, 5.2。
"""

import logging
import re
import uuid
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource, ClaimEvidence, ClaimVerdict
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class EvidenceQualityScorer(BaseScorer):
    """证据质量评分器（含 claim-evidence grounding）"""

    @property
    def name(self) -> str:
        return "evidence_quality"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.EVIDENCE

    @property
    def version(self) -> str:
        return "2.1.0"

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """执行证据质量评分，包含 claim-evidence grounding"""
        # 从 trace 事件中提取证据相关事件
        evidence_events = [
            e for e in trace_events
            if e.get("event_type") in ("evidence", "retrieval", "citation")
        ]

        output_data = trial_data.get("output_data", {})
        output_text = ""
        if isinstance(output_data, dict):
            output_text = output_data.get("content", "") or output_data.get("result", "")

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

        # ===== Claim 抽取 (5.1) =====
        claims = self._extract_claims(output_text, evidence_events)

        # ===== Claim -> Evidence 映射 (5.2) =====
        claims = self._map_claims_to_evidence(claims, evidence_events, trace_events)

        # ===== 综合评分 =====
        dimensions = {}
        reasons = []

        # 证据覆盖率
        total_claims = max(1, len(claims))
        supported_claims = sum(
            1 for c in claims
            if c.verdict in (ClaimVerdict.SUPPORTED, ClaimVerdict.WEAKLY_SUPPORTED)
        )
        coverage = supported_claims / total_claims if total_claims > 0 else 0.0
        dimensions["evidence_coverage"] = round(coverage, 4)

        if coverage < 0.3:
            reasons.append(f"证据覆盖率低 ({coverage:.0%})，{supported_claims}/{total_claims} 条 claim 有证据支撑")

        # 矛盾检测
        contradicted_count = sum(1 for c in claims if c.verdict == ClaimVerdict.CONTRADICTED)
        if contradicted_count > 0:
            reasons.append(f"发现 {contradicted_count} 条与证据矛盾的 claim")
            dimensions["contradiction_ratio"] = round(contradicted_count / total_claims, 4)

        # 无证据断言
        unsupported_count = sum(1 for c in claims if c.verdict == ClaimVerdict.UNSUPPORTED)
        dimensions["unsupported_ratio"] = round(unsupported_count / total_claims, 4) if total_claims > 0 else 0.0

        # 引用相关性
        relevant_count = 0
        for event in evidence_events:
            data = event.get("data", {})
            if data.get("query") or data.get("topic") or data.get("source"):
                relevant_count += 1
        relevance = relevant_count / max(1, len(evidence_events)) if evidence_events else 0.5
        dimensions["citation_relevance"] = round(relevance, 4)

        # 来源一致性
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
            "evidence_coverage": 0.35,
            "citation_relevance": 0.20,
            "unsupported_ratio": 0.25,  # 越低越好，取反
            "source_consistency": 0.10,
        }

        # unsupported_ratio 需要取反（越低越好）
        overall_score = (
            dimensions["evidence_coverage"] * 0.35
            + dimensions["citation_relevance"] * 0.20
            + (1.0 - dimensions.get("unsupported_ratio", 0)) * 0.25
            + dimensions["source_consistency"] * 0.10
            - (dimensions.get("contradiction_ratio", 0) * 0.10)
        )
        overall_score = max(0.0, min(1.0, overall_score))

        reason_text = "; ".join(reasons) if reasons else f"证据质量良好，综合得分 {overall_score:.2f}"

        return ScoreResult(
            score_name=self.name,
            score=overall_score,
            passed=overall_score >= 0.6,
            reason=reason_text,
            confidence=0.8 if evidence_events else 0.5,
            source=self.source,
            version=self.version,
            claims=claims,
            evidence_refs=[e.get("event_id", "") for e in evidence_events[:10]],
            raw_output={"dimensions": dimensions, "claim_count": len(claims)},
        )

    def _extract_claims(self, output_text: str, evidence_events: List[Dict[str, Any]]) -> List[ClaimEvidence]:
        """从输出文本中提取可验证的 claim (5.1)

        使用基于句子的启发式方法：
        - 按句号/感叹号分割句子
        - 过滤掉过短或纯数字的句子
        - 每个有效句子作为一个 claim
        """
        if not output_text:
            return []

        # 按中文/英文句号、感叹号、问号分割
        sentences = re.split(r'[。！？.!?\n]', output_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) >= 8]

        claims = []
        for i, sentence in enumerate(sentences[:20]):  # 限制最多20条claim
            claim = ClaimEvidence(
                claim_id=f"claim_{uuid.uuid4().hex[:8]}",
                claim_text=sentence,
                verdict=ClaimVerdict.UNSUPPORTED,  # 默认未支撑，后续映射时更新
                confidence=0.0,
                reason="待证据映射",
            )
            claims.append(claim)

        return claims

    @staticmethod
    def _tokenize_chinese(text: str) -> set:
        """中文文本分词：使用 2-gram 滑动窗口 + 英文单词"""
        tokens = set()
        # 提取英文单词
        for w in re.findall(r'[a-zA-Z]{3,}', text):
            tokens.add(w.lower())
        # 提取连续中文字符段，然后生成 2-gram
        for segment in re.findall(r'[一-鿿]+', text):
            for i in range(len(segment) - 1):
                tokens.add(segment[i:i+2])
            # 也加入 3-gram 增加区分度
            for i in range(len(segment) - 2):
                tokens.add(segment[i:i+3])
        return tokens

    def _map_claims_to_evidence(
        self,
        claims: List[ClaimEvidence],
        evidence_events: List[Dict[str, Any]],
        all_trace_events: List[Dict[str, Any]],
    ) -> List[ClaimEvidence]:
        """将 claim 映射到证据 (5.2)

        使用 n-gram 重叠和字符级匹配启发式方法：
        - 对 claim 和证据文本分别做 2/3-gram 分词
        - 计算 Jaccard 相似度
        - 根据相似度阈值判定 supported / weakly_supported / unsupported
        """
        if not evidence_events:
            for claim in claims:
                claim.prediction_label = True
                claim.prediction_reason = "未找到可用证据"
            return claims

        # 构建证据索引
        evidence_items = []
        for event in evidence_events:
            data = event.get("data", {})
            snippet = data.get("snippet") or data.get("content") or data.get("text") or ""
            source = data.get("source") or data.get("provider") or ""
            query = data.get("query") or data.get("topic") or ""
            event_id = event.get("event_id", "")

            # 合并所有文本做分词
            combined_text = " ".join(filter(None, [snippet, query, source]))
            keywords = self._tokenize_chinese(combined_text)

            evidence_items.append({
                "snippet": snippet[:500] if snippet else "",
                "source": source,
                "query": query,
                "event_id": event_id,
                "keywords": keywords,
            })

        # 对每条 claim 进行证据匹配
        for claim in claims:
            claim_tokens = self._tokenize_chinese(claim.claim_text)

            best_match = None
            best_overlap = 0

            for ev in evidence_items:
                if not ev["keywords"]:
                    continue
                overlap = len(claim_tokens & ev["keywords"])
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = ev

            total_claim_tokens = max(1, len(claim_tokens))
            overlap_ratio = best_overlap / total_claim_tokens

            if best_match and overlap_ratio >= 0.3:
                # 足够重叠 → supported
                claim.verdict = ClaimVerdict.SUPPORTED
                claim.confidence = min(1.0, overlap_ratio + 0.3)
                claim.evidence_snippet = best_match["snippet"][:200]
                claim.evidence_source = best_match["source"]
                claim.trace_event_id = best_match["event_id"]
                claim.reason = f"n-gram 重叠率 {overlap_ratio:.0%}，证据充分"
            elif best_match and overlap_ratio >= 0.1:
                # 部分重叠 → weakly_supported
                claim.verdict = ClaimVerdict.WEAKLY_SUPPORTED
                claim.confidence = min(0.6, overlap_ratio + 0.1)
                claim.evidence_snippet = best_match["snippet"][:200]
                claim.evidence_source = best_match["source"]
                claim.trace_event_id = best_match["event_id"]
                claim.reason = f"n-gram 重叠率 {overlap_ratio:.0%}，证据较弱"
            else:
                # 无匹配 → unsupported
                claim.verdict = ClaimVerdict.UNSUPPORTED
                claim.confidence = 0.8
                claim.reason = "未在可用证据中找到支撑信息"

            # 预测标签与人工真值分离，避免评分器 verdict 被误当成 ground truth。
            claim.prediction_label = claim.verdict in (
                ClaimVerdict.UNSUPPORTED,
                ClaimVerdict.CONTRADICTED,
            )
            claim.prediction_reason = claim.reason

        return claims
