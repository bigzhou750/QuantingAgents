"""
DeepEval 适配器

将 DeepEval 库的指标评分接入统一 eval_score 结构。
如果 DeepEval 未安装，优雅降级并记录警告。

对应 spec 二期任务 2.5。
"""

import logging
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class DeepEvalAdapter(BaseScorer):
    """DeepEval 适配器评分器"""

    def __init__(self, metrics: Optional[List[str]] = None):
        """
        Args:
            metrics: 要运行的 DeepEval 指标列表。
                     默认使用 ["AnswerRelevancyMetric", "FaithfulnessMetric"]。
        """
        self._metrics = metrics or ["AnswerRelevancyMetric", "FaithfulnessMetric"]
        self._available = False
        try:
            import deepeval  # noqa: F401
            self._available = True
        except ImportError:
            logger.info("DeepEval not installed, adapter will return skipped results")

    @property
    def name(self) -> str:
        return "deepeval"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.RULE_BASED  # DeepEval 本质是规则+模型混合

    @property
    def version(self) -> str:
        return "1.0.0"

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """执行 DeepEval 评分"""
        if not self._available:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="DeepEval 未安装，跳过评分。请 pip install deepeval",
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

        if not query or not actual_output:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="缺少输入或输出，无法运行 DeepEval 指标",
                confidence=1.0,
                source=self.source,
                version=self.version,
            )

        try:
            scores = {}
            reasons = []

            for metric_name in self._metrics:
                metric_result = await self._run_metric(metric_name, query, actual_output)
                if metric_result is not None:
                    scores[metric_name] = metric_result["score"]
                    if not metric_result["passed"]:
                        reasons.append(f"{metric_name}: {metric_result.get('reason', 'failed')}")

            if not scores:
                return ScoreResult(
                    score_name=self.name,
                    score=0.0,
                    passed=False,
                    reason="所有 DeepEval 指标均未能运行",
                    confidence=0.0,
                    source=self.source,
                    version=self.version,
                )

            overall = sum(scores.values()) / len(scores)
            reason_text = "; ".join(reasons) if reasons else f"DeepEval {len(scores)} 项指标全部通过"

            return ScoreResult(
                score_name=self.name,
                score=max(0.0, min(1.0, overall)),
                passed=overall >= 0.6,
                reason=reason_text,
                confidence=0.9,
                source=self.source,
                version=self.version,
                raw_output={"metric_scores": scores},
            )

        except Exception as e:
            logger.error(f"DeepEval scoring failed: {e}")
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason=f"DeepEval 执行异常: {str(e)}",
                confidence=0.0,
                source=self.source,
                version=self.version,
            )

    async def _run_metric(
        self, metric_name: str, query: str, actual_output: str
    ) -> Optional[Dict[str, Any]]:
        """运行单个 DeepEval 指标"""
        try:
            import deepeval
            from deepeval.test_case import LLMTestCase

            test_case = LLMTestCase(input=query, actual_output=actual_output)

            metric_class = getattr(deepeval.metrics, metric_name, None)
            if not metric_class:
                logger.warning(f"Unknown DeepEval metric: {metric_name}")
                return None

            metric = metric_class(threshold=0.6)
            metric.measure(test_case)

            return {
                "score": float(metric.score) if hasattr(metric, "score") else 0.0,
                "passed": bool(metric.is_successful()) if hasattr(metric, "is_successful") else False,
                "reason": getattr(metric, "reason", ""),
            }

        except Exception as e:
            logger.warning(f"Failed to run DeepEval metric {metric_name}: {e}")
            return None
