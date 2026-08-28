"""
Ragas 适配器

将 Ragas 库的证据/检索质量评分接入统一 eval_score 结构。
与自研 EvidenceQualityScorer 并存，不覆盖原始评分。
如果 Ragas 未安装，优雅降级。

对应 spec 二期任务 2.6。
"""

import logging
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class RagasAdapter(BaseScorer):
    """Ragas 适配器评分器"""

    def __init__(self, metrics: Optional[List[str]] = None):
        """
        Args:
            metrics: 要运行的 Ragas 指标列表。
                     默认使用 ["faithfulness", "answer_relevancy"]。
        """
        self._metrics = metrics or ["faithfulness", "answer_relevancy"]
        self._available = False
        try:
            import ragas  # noqa: F401
            self._available = True
        except ImportError:
            logger.info("Ragas not installed, adapter will return skipped results")

    @property
    def name(self) -> str:
        return "ragas"

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
        """执行 Ragas 评分"""
        if not self._available:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="Ragas 未安装，跳过评分。请 pip install ragas",
                confidence=0.0,
                source=self.source,
                version=self.version,
            )

        input_data = trial_data.get("input_data", {})
        output_data = trial_data.get("output_data", {})

        query = input_data.get("prompt", "")
        actual_output = ""
        if isinstance(output_data, dict):
            actual_output = output_data.get("content", "")

        # 从 trace 事件中提取检索到的上下文
        contexts = self._extract_contexts(trace_events)

        if not query or not actual_output:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="缺少输入或输出，无法运行 Ragas 指标",
                confidence=1.0,
                source=self.source,
                version=self.version,
            )

        try:
            scores = {}
            reasons = []

            for metric_name in self._metrics:
                metric_result = await self._run_metric(
                    metric_name, query, actual_output, contexts
                )
                if metric_result is not None:
                    scores[metric_name] = metric_result["score"]
                    if metric_result["score"] < 0.6:
                        reasons.append(f"{metric_name}: {metric_result['score']:.2f}")

            if not scores:
                return ScoreResult(
                    score_name=self.name,
                    score=0.0,
                    passed=False,
                    reason="所有 Ragas 指标均未能运行",
                    confidence=0.0,
                    source=self.source,
                    version=self.version,
                )

            overall = sum(scores.values()) / len(scores)
            reason_text = "; ".join(reasons) if reasons else f"Ragas {len(scores)} 项指标评分完成"

            return ScoreResult(
                score_name=self.name,
                score=max(0.0, min(1.0, overall)),
                passed=overall >= 0.6,
                reason=reason_text,
                confidence=0.85,
                source=self.source,
                version=self.version,
                raw_output={"metric_scores": scores},
            )

        except Exception as e:
            logger.error(f"Ragas scoring failed: {e}")
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason=f"Ragas 执行异常: {str(e)}",
                confidence=0.0,
                source=self.source,
                version=self.version,
            )

    def _extract_contexts(self, trace_events: List[Dict[str, Any]]) -> List[str]:
        """从 trace 事件中提取检索到的上下文片段"""
        contexts = []
        for event in trace_events:
            if event.get("event_type") in ("retrieval", "evidence"):
                data = event.get("data", {})
                content = data.get("content") or data.get("text") or data.get("snippet", "")
                if content:
                    contexts.append(str(content))
        return contexts

    async def _run_metric(
        self,
        metric_name: str,
        query: str,
        actual_output: str,
        contexts: List[str],
    ) -> Optional[Dict[str, Any]]:
        """运行单个 Ragas 指标"""
        try:
            from ragas.metrics import faithfulness, answer_relevancy
            from ragas.testset import TestSample

            metric_map = {
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
            }

            metric = metric_map.get(metric_name)
            if not metric:
                logger.warning(f"Unknown Ragas metric: {metric_name}")
                return None

            sample = TestSample(
                user_input=query,
                response=actual_output,
                retrieved_contexts=contexts if contexts else [query],
            )

            score = await metric.single_turn_ascore(sample)

            return {
                "score": float(score),
                "passed": float(score) >= 0.6,
            }

        except Exception as e:
            logger.warning(f"Failed to run Ragas metric {metric_name}: {e}")
            return None
