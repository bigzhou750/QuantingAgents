"""
评分器中心

提供统一的评分器接口和插件式评分器管理。
支持规则评分、金融规则评分、证据评分、安全评分、LLM-as-judge 和人工复核。
"""

import logging
from typing import Optional, List, Dict, Any, Protocol, runtime_checkable
from datetime import datetime
from enum import Enum

from app.core.database import get_mongo_db
from app.models.eval import ScoreSource, EvalScore
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


@runtime_checkable
class Scorer(Protocol):
    """评分器协议"""

    @property
    def name(self) -> str:
        """评分器名称"""
        ...

    @property
    def source(self) -> ScoreSource:
        """评分来源"""
        ...

    @property
    def version(self) -> str:
        """评分器版本"""
        ...

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """执行评分"""
        ...


class ScorerHub:
    """评分器中心"""

    COLLECTION_SCORES = "eval_scores"

    def __init__(self):
        self._initialized = False
        self._scorers: Dict[str, Scorer] = {}

    async def initialize(self):
        """初始化评分器中心，创建索引并注册默认评分器"""
        if self._initialized:
            return

        logger.info("Initializing ScorerHub")
        db = get_mongo_db()

        # 创建索引
        await db[self.COLLECTION_SCORES].create_index("score_id", unique=True)
        await db[self.COLLECTION_SCORES].create_index("trial_id")
        await db[self.COLLECTION_SCORES].create_index([("trial_id", 1), ("score_name", 1)])
        await db[self.COLLECTION_SCORES].create_index("source")

        # 注册默认评分器
        await self._register_default_scorers()

        self._initialized = True
        logger.info(f"ScorerHub initialized with {len(self._scorers)} scorers")

    async def _register_default_scorers(self):
        """注册默认评分器"""
        try:
            from app.services.eval.scorers.rule_scorer import RuleBasedScorer
            from app.services.eval.scorers.output_scorer import OutputCompletenessScorer

            self.register_scorer(RuleBasedScorer())
            self.register_scorer(OutputCompletenessScorer())

            logger.info("Registered default scorers: rule_based, output_completeness")
        except ImportError as e:
            logger.warning(f"Failed to import default scorers: {e}")

    def register_scorer(self, scorer: Scorer) -> None:
        """注册评分器"""
        key = f"{scorer.source.value}:{scorer.name}"
        self._scorers[key] = scorer
        logger.info(f"Registered scorer: {key} (v{scorer.version})")

    def get_scorer(self, source: ScoreSource, name: str) -> Optional[Scorer]:
        """获取评分器"""
        key = f"{source.value}:{name}"
        return self._scorers.get(key)

    def list_scorers(self) -> List[Dict[str, Any]]:
        """列出所有评分器"""
        return [
            {
                "name": s.name,
                "source": s.source.value,
                "version": s.version,
            }
            for s in self._scorers.values()
        ]

    async def score_trial(
        self,
        trial_id: str,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        scorer_names: Optional[List[str]] = None,
        case_config: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        对 trial 执行评分并保存结果

        Args:
            trial_id: trial ID
            trial_data: trial 数据
            trace_events: trace 事件列表
            scorer_names: 指定评分器名称列表，None 表示使用全部
            case_config: case 级别的评分配置

        Returns:
            评分结果列表
        """
        import uuid

        results = []
        db = get_mongo_db()

        for key, scorer in self._scorers.items():
            # 如果指定了评分器列表，只运行指定的
            if scorer_names and scorer.name not in scorer_names:
                continue

            try:
                result = await scorer.score(trial_data, trace_events, case_config)

                # 转换为字典格式
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                else:
                    result_dict = dict(result)

                # 生成评分 ID
                score_id = f"score_{uuid.uuid4().hex[:12]}"

                # 保存到数据库
                score_doc = EvalScore(
                    score_id=score_id,
                    trial_id=trial_id,
                    score_name=result_dict["score_name"],
                    score=result_dict["score"],
                    passed=result_dict["passed"],
                    reason=result_dict["reason"],
                    confidence=result_dict.get("confidence", 1.0),
                    source=ScoreSource(result_dict["source"]),
                    scorer_version=result_dict.get("version", "1.0.0"),
                    evidence_refs=result_dict.get("evidence_refs", []),
                    raw_output=result_dict.get("raw_output"),
                )

                await db[self.COLLECTION_SCORES].insert_one(
                    score_doc.model_dump(by_alias=True, exclude={"id"})
                )

                result_dict["score_id"] = score_id
                results.append(result_dict)

                logger.debug(f"Scored trial {trial_id} with {scorer.name}: {result_dict['score']:.2f}")

            except Exception as e:
                logger.error(f"Scorer {key} failed for trial {trial_id}: {e}")
                results.append({
                    "score_name": scorer.name,
                    "score": 0.0,
                    "passed": False,
                    "reason": f"Scorer error: {str(e)}",
                    "confidence": 0.0,
                    "source": scorer.source.value,
                    "version": scorer.version,
                })

        return results

    async def get_trial_scores(self, trial_id: str) -> List[Dict[str, Any]]:
        """获取某个 trial 的所有评分结果"""
        db = get_mongo_db()

        cursor = db[self.COLLECTION_SCORES].find({"trial_id": trial_id}).sort("created_at", 1)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def get_score_summary(self, trial_id: str) -> Dict[str, Any]:
        """获取某个 trial 的评分摘要"""
        scores = await self.get_trial_scores(trial_id)

        if not scores:
            return {"total_scores": 0, "average_score": 0.0, "passed_count": 0}

        total_score = sum(s["score"] for s in scores)
        passed_count = sum(1 for s in scores if s["passed"])

        return {
            "total_scores": len(scores),
            "average_score": round(total_score / len(scores), 4),
            "passed_count": passed_count,
            "failed_count": len(scores) - passed_count,
            "by_source": {
                source: {
                    "count": len([s for s in scores if s["source"] == source]),
                    "avg_score": round(
                        sum(s["score"] for s in scores if s["source"] == source) /
                        max(1, len([s for s in scores if s["source"] == source])),
                        4
                    ),
                }
                for source in set(s["source"] for s in scores)
            },
        }


# 单例实例
scorer_hub = ScorerHub()
