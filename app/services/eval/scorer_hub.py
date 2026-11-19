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
from app.models.eval import ScoreSource, ScoreStatus, EvalScore
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
        registered = []

        try:
            from app.services.eval.scorers.rule_scorer import RuleBasedScorer
            from app.services.eval.scorers.output_scorer import OutputCompletenessScorer

            self.register_scorer(RuleBasedScorer())
            self.register_scorer(OutputCompletenessScorer())
            from app.services.eval.scorers.expected_content_scorer import ExpectedContentScorer
            self.register_scorer(ExpectedContentScorer())
            registered.extend(["rule_based", "output_completeness", "expected_content"])
        except ImportError as e:
            logger.warning(f"Failed to import base scorers: {e}")

        # 二期评分器
        try:
            from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer
            self.register_scorer(LLMJudgeScorer())
            registered.append("llm_judge")
        except ImportError as e:
            logger.warning(f"Failed to import llm_judge_scorer: {e}")

        try:
            from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer
            self.register_scorer(EvidenceQualityScorer())
            registered.append("evidence_quality")
        except ImportError as e:
            logger.warning(f"Failed to import evidence_scorer: {e}")

        try:
            from app.services.eval.scorers.trajectory_scorer import TrajectoryScorer
            self.register_scorer(TrajectoryScorer())
            registered.append("trajectory")
        except ImportError as e:
            logger.warning(f"Failed to import trajectory_scorer: {e}")

        try:
            from app.services.eval.scorers.skill_route_scorer import SkillRouteScorer
            from app.services.eval.scorers.skill_execution_scorer import SkillExecutionScorer
            from app.services.eval.scorers.skill_coexistence_scorer import SkillCoexistenceScorer
            self.register_scorer(SkillRouteScorer())
            self.register_scorer(SkillExecutionScorer())
            self.register_scorer(SkillCoexistenceScorer())
            registered.extend(["skill_route", "skill_execution", "skill_coexistence"])
        except ImportError as e:
            logger.warning(f"Failed to import skill scorers: {e}")

        try:
            from app.services.eval.scorers.safety_scorer import SafetyScorer
            self.register_scorer(SafetyScorer())
            registered.append("safety")
        except ImportError as e:
            logger.warning(f"Failed to import safety_scorer: {e}")

        try:
            from app.services.eval.scorers.redteam_adapter import RedTeamAdapter
            self.register_scorer(RedTeamAdapter())
            registered.append("redteam")
        except ImportError as e:
            logger.warning(f"Failed to import redteam_adapter: {e}")

        # 外部库适配器（未安装时优雅降级）
        try:
            from app.services.eval.scorers.deepeval_adapter import DeepEvalAdapter
            self.register_scorer(DeepEvalAdapter())
            registered.append("deepeval")
        except ImportError as e:
            logger.warning(f"Failed to import deepeval_adapter: {e}")

        try:
            from app.services.eval.scorers.ragas_adapter import RagasAdapter
            self.register_scorer(RagasAdapter())
            registered.append("ragas")
        except ImportError as e:
            logger.warning(f"Failed to import ragas_adapter: {e}")

        logger.info(f"Registered default scorers: {', '.join(registered)}")

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
        """列出所有评分器及其可用状态

        返回每个评分器的 name、source、version 和 status。
        status 为 'available' 表示已注册且可用；
        'not_configured' 表示依赖未安装或未启用。
        """
        result = []
        for s in self._scorers.values():
            # 检查适配器是否有 availability 标志（外部库适配器）
            is_available = True
            if hasattr(s, '_available'):
                is_available = bool(s._available)
            elif hasattr(s, 'is_available'):
                try:
                    is_available = bool(s.is_available)
                except Exception:
                    is_available = False

            result.append({
                "name": s.name,
                "source": s.source.value,
                "version": s.version,
                "status": "available" if is_available else "not_configured",
            })
        return result

    async def score_trial(
        self,
        trial_id: str,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        scorer_names: Optional[List[str]] = None,
        case_config: Optional[Dict[str, Any]] = None,
        run_config: Optional[Dict[str, Any]] = None,
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
            # 如果指定了评分器列表，只运行指定的 → skipped
            if scorer_names and scorer.name not in scorer_names:
                score_id = f"score_{uuid.uuid4().hex[:12]}"
                skipped_doc = EvalScore(
                    score_id=score_id,
                    trial_id=trial_id,
                    score_name=scorer.name,
                    score=0.0,
                    passed=False,
                    status=ScoreStatus.SKIPPED,
                    reason="Scorer not selected for this run",
                    confidence=0.0,
                    source=scorer.source,
                    scorer_version=scorer.version,
                )
                await db[self.COLLECTION_SCORES].insert_one(
                    skipped_doc.model_dump(by_alias=True, exclude={"id"})
                )
                results.append({
                    "score_id": score_id,
                    "score_name": scorer.name,
                    "score": 0.0,
                    "passed": False,
                    "status": ScoreStatus.SKIPPED.value,
                    "reason": "Scorer not selected for this run",
                    "confidence": 0.0,
                    "source": scorer.source.value,
                    "version": scorer.version,
                })
                continue

            active_scorer = scorer
            if scorer.name == "llm_judge" and run_config:
                try:
                    from app.services.eval.judge_config import resolve_default_judge_model
                    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer

                    active_scorer = LLMJudgeScorer(
                        judge_model=run_config.get("judge_model")
                        or getattr(scorer, "_judge_model", None)
                        or resolve_default_judge_model(),
                        rubric=run_config.get("rubric") or getattr(scorer, "_rubric", None),
                        version=run_config.get("rubric_version") or getattr(scorer, "_version", "1.0.0"),
                    )
                except Exception as exc:
                    logger.warning(f"Failed to build run-scoped judge scorer: {exc}")

            # 检查外部库适配器是否可用 → not_configured
            is_available = True
            if hasattr(active_scorer, '_available'):
                is_available = bool(active_scorer._available)
            elif hasattr(active_scorer, 'is_available'):
                try:
                    is_available = bool(active_scorer.is_available)
                except Exception:
                    is_available = False

            if not is_available:
                score_id = f"score_{uuid.uuid4().hex[:12]}"
                nc_doc = EvalScore(
                    score_id=score_id,
                    trial_id=trial_id,
                    score_name=scorer.name,
                    score=0.0,
                    passed=False,
                    status=ScoreStatus.NOT_CONFIGURED,
                    reason=f"Scorer dependency not installed or not enabled",
                    confidence=0.0,
                    source=scorer.source,
                    scorer_version=scorer.version,
                )
                await db[self.COLLECTION_SCORES].insert_one(
                    nc_doc.model_dump(by_alias=True, exclude={"id"})
                )
                results.append({
                    "score_id": score_id,
                    "score_name": scorer.name,
                    "score": 0.0,
                    "passed": False,
                    "status": ScoreStatus.NOT_CONFIGURED.value,
                    "reason": f"Scorer dependency not installed or not enabled",
                    "confidence": 0.0,
                    "source": scorer.source.value,
                    "version": scorer.version,
                })
                continue

            try:
                result = await active_scorer.score(trial_data, trace_events, case_config)

                # 转换为字典格式
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                else:
                    result_dict = dict(result)

                # 生成评分 ID
                score_id = f"score_{uuid.uuid4().hex[:12]}"

                # 根据分数和通过状态确定 score status
                status_value = result_dict.get("scoring_status") or result_dict.get("status")
                if status_value:
                    try:
                        score_status = ScoreStatus(status_value)
                    except ValueError:
                        score_status = (
                            ScoreStatus.PASSED
                            if result_dict.get("passed", False)
                            else ScoreStatus.FAILED
                        )
                else:
                    score_status = (
                        ScoreStatus.PASSED
                        if result_dict.get("passed", False)
                        else ScoreStatus.FAILED
                    )

                # 解析 claims（如果评分器返回了 claim-evidence 结构）
                from app.models.eval import ClaimEvidence
                claims_data = result_dict.get("claims", [])
                claims = []
                if claims_data:
                    for c in claims_data:
                        if isinstance(c, dict):
                            try:
                                claims.append(ClaimEvidence(**c))
                            except Exception:
                                pass
                        elif isinstance(c, ClaimEvidence):
                            claims.append(c)

                # 保存到数据库
                score_doc = EvalScore(
                    score_id=score_id,
                    trial_id=trial_id,
                    score_name=result_dict["score_name"],
                    score=result_dict["score"],
                    passed=result_dict["passed"],
                    status=score_status,
                    reason=result_dict["reason"],
                    confidence=result_dict.get("confidence", 1.0),
                    source=ScoreSource(result_dict["source"]),
                    scorer_version=result_dict.get("version", active_scorer.version),
                    evidence_refs=result_dict.get("evidence_refs", []),
                    claims=claims,
                    raw_output=result_dict.get("raw_output"),
                )

                await db[self.COLLECTION_SCORES].insert_one(
                    score_doc.model_dump(by_alias=True, exclude={"id"})
                )

                result_dict["score_id"] = score_id
                result_dict["status"] = score_status.value
                results.append(result_dict)

                logger.debug(f"Scored trial {trial_id} with {active_scorer.name}: {result_dict['score']:.2f}")

            except Exception as e:
                logger.error(f"Scorer {active_scorer.name} failed for trial {trial_id}: {e}")
                # 评分器执行出错 → error 状态，持久化到数据库
                score_id = f"score_{uuid.uuid4().hex[:12]}"
                error_doc = EvalScore(
                    score_id=score_id,
                    trial_id=trial_id,
                    score_name=scorer.name,
                    score=0.0,
                    passed=False,
                    status=ScoreStatus.ERROR,
                    reason=f"Scorer error: {str(e)}",
                    confidence=0.0,
                    source=scorer.source,
                    scorer_version=scorer.version,
                )
                await db[self.COLLECTION_SCORES].insert_one(
                    error_doc.model_dump(by_alias=True, exclude={"id"})
                )
                results.append({
                    "score_id": score_id,
                    "score_name": scorer.name,
                    "score": 0.0,
                    "passed": False,
                    "status": ScoreStatus.ERROR.value,
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
        """获取某个 trial 的评分摘要

        区分真实评分（passed/failed）和非真实评分（skipped/not_configured/error），
        避免未启用的评分器被误当成真实低分。
        """
        scores = await self.get_trial_scores(trial_id)

        if not scores:
            return {
                "total_scores": 0,
                "effective_scores": 0,
                "average_score": 0.0,
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "not_configured_count": 0,
                "error_count": 0,
            }

        # 按状态分类
        real_statuses = {ScoreStatus.PASSED.value, ScoreStatus.FAILED.value}
        effective_scores = [s for s in scores if s.get("status") in real_statuses]
        skipped_scores = [s for s in scores if s.get("status") == ScoreStatus.SKIPPED.value]
        nc_scores = [s for s in scores if s.get("status") == ScoreStatus.NOT_CONFIGURED.value]
        error_scores = [s for s in scores if s.get("status") == ScoreStatus.ERROR.value]
        unscorable_scores = [s for s in scores if s.get("status") == ScoreStatus.UNSCORABLE.value]
        not_applicable_scores = [s for s in scores if s.get("status") == ScoreStatus.NOT_APPLICABLE.value]

        # 旧数据可能没有 status 字段，兼容处理
        no_status_scores = [s for s in scores if "status" not in s or s.get("status") is None]
        if no_status_scores:
            effective_scores.extend(no_status_scores)

        passed_count = sum(1 for s in effective_scores if s.get("passed", False))
        failed_count = len(effective_scores) - passed_count

        avg_score = 0.0
        if effective_scores:
            avg_score = round(sum(s["score"] for s in effective_scores) / len(effective_scores), 4)

        return {
            "total_scores": len(scores),
            "effective_scores": len(effective_scores),
            "average_score": avg_score,
            "passed_count": passed_count,
            "failed_count": failed_count,
                "skipped_count": len(skipped_scores),
                "not_configured_count": len(nc_scores),
                "error_count": len(error_scores),
                "unscorable_count": len(unscorable_scores),
                "not_applicable_count": len(not_applicable_scores),
                "by_source": {
                source: {
                    "count": len([s for s in effective_scores if s["source"] == source]),
                    "avg_score": round(
                        sum(s["score"] for s in effective_scores if s["source"] == source) /
                        max(1, len([s for s in effective_scores if s["source"] == source])),
                        4
                    ),
                }
                for source in set(s["source"] for s in effective_scores)
            },
        }


# 单例实例
scorer_hub = ScorerHub()
