"""
候选提案生成与管理服务

根据触发器输入的失败信息，生成针对特定 artifact 的候选变更提案。
包含失败归因、变更面映射、forbidden target 拦截等核心逻辑。
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.evolution import (
    Proposal,
    ProposalStatus,
    ArtifactType,
    TriggerType,
    RiskLevel,
)
from app.services.evolution.artifact_registry import artifact_registry
from app.services.evolution.clustering import identify_primary_failure_surface
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class ProposalService:
    """候选提案服务"""

    COLLECTION = "evolution_proposals"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务和索引"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("proposal_id", unique=True)
        await db[self.COLLECTION].create_index("status")
        await db[self.COLLECTION].create_index("target_artifact_id")
        await db[self.COLLECTION].create_index("trigger_type")
        await db[self.COLLECTION].create_index("created_at")
        self._initialized = True
        logger.info("ProposalService initialized")

    async def create_from_trigger(self, trigger_info: Dict[str, Any]) -> Optional[Proposal]:
        """从触发器信息创建候选提案

        Args:
            trigger_info: trigger_service 返回的触发信息字典
        Returns:
            创建的 Proposal 或 None（如果被 forbidden 拦截）
        """
        trigger_type_str = trigger_info.get("trigger_type", "run_completed")
        trigger_run_id = trigger_info.get("trigger_run_id", "")
        dataset_id = trigger_info.get("dataset_id", "")
        target_surface = trigger_info.get("target_surface", "unknown")
        sample_failure_ids = trigger_info.get("sample_failure_ids", [])

        # 映射失败面到 artifact type
        artifact_type = self._surface_to_artifact_type(target_surface)

        # 确定目标 artifact ID
        target_artifact_id = await self._resolve_target_artifact(
            artifact_type, dataset_id, trigger_info
        )

        # 检查 forbidden target
        forbidden = self._check_forbidden(target_artifact_id)

        # 生成候选 diff
        diff = self._generate_candidate_diff(artifact_type, target_surface, trigger_info)

        # 评估风险等级
        risk_level = self._assess_risk(trigger_info, artifact_type)

        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"

        proposal = Proposal(
            proposal_id=proposal_id,
            trigger_run_id=trigger_run_id,
            trigger_type=TriggerType(trigger_type_str),
            target_artifact_id=target_artifact_id,
            target_artifact_type=artifact_type,
            diff=diff,
            reason=self._build_reason(target_surface, trigger_info),
            sample_failure_ids=sample_failure_ids[:20],
            impact_estimate=self._estimate_impact(artifact_type, target_artifact_id),
            budget_estimate={"verification_runs": 1, "estimated_cost_usd": 0.5},
            risk_level=risk_level,
            rollback_strategy="restore_previous_version",
            status=ProposalStatus.DRAFT if forbidden else ProposalStatus.PENDING_VERIFY,
            forbidden_target=forbidden,
            created_by="system",
        )

        db = get_mongo_db()
        await db[self.COLLECTION].insert_one(proposal.model_dump(by_alias=True, exclude={"id"}))

        # 记录事件日志
        await self._log_event("proposal_created", proposal_id, {
            "trigger_type": trigger_type_str,
            "target_artifact": target_artifact_id,
            "forbidden": forbidden,
        })

        logger.info(f"[Evolution] Created proposal {proposal_id} for {target_artifact_id} ({'FORBIDDEN' if forbidden else 'pending verify'})")
        return proposal

    def _surface_to_artifact_type(self, surface: str) -> ArtifactType:
        """将失败面映射到 artifact 类型"""
        mapping = {
            "skill": ArtifactType.SKILL,
            "prompt": ArtifactType.PROMPT,
            "policy": ArtifactType.POLICY,
            "rubric": ArtifactType.RUBRIC,
            "case": ArtifactType.CASE,
        }
        return mapping.get(surface, ArtifactType.SKILL)

    async def _resolve_target_artifact(
        self, artifact_type: ArtifactType, dataset_id: str, trigger_info: Dict[str, Any]
    ) -> str:
        """解析目标 artifact ID"""
        clustering = trigger_info.get("clustering", {})
        by_scorer = clustering.get("by_scorer", [])

        if artifact_type == ArtifactType.CASE:
            return f"art_case_dataset_{dataset_id}"

        if artifact_type == ArtifactType.RUBRIC:
            return "art_rubric_financial_default"

        if artifact_type == ArtifactType.POLICY:
            # 根据 top scorer 细化
            if by_scorer:
                top = by_scorer[0].get("scorer", "")
                if "evidence" in top or "grounding" in top:
                    return "art_policy_grounding"
                if "safety" in top:
                    return "art_policy_safety"
            return "art_policy_routing_default"

        if artifact_type == ArtifactType.PROMPT:
            return "art_prompt_system_default"

        # Skill: 尝试从失败聚类推断具体 skill
        if by_scorer and artifact_type == ArtifactType.SKILL:
            # 默认通用 skill 优化
            pass
        return "art_skill_general"

    def _check_forbidden(self, artifact_id: str) -> bool:
        """检查目标是否在禁止列表中"""
        forbidden_list = [
            t.strip() for t in settings.EVOLUTION_FORBIDDEN_TARGETS.split(",") if t.strip()
        ]
        if artifact_id in forbidden_list:
            return True

        # 硬编码安全边界：核心代码、测试集、评分口径
        hardcoded_forbidden = [
            "core_code", "test_split", "scorer_definition",
            "eval_platform_config", "admin_credentials",
        ]
        for pattern in hardcoded_forbidden:
            if pattern in artifact_id.lower():
                return True

        return False

    def _generate_candidate_diff(
        self, artifact_type: ArtifactType, surface: str, trigger_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成候选变更描述"""
        clustering = trigger_info.get("clustering", {})
        by_error = clustering.get("by_error", [])
        by_scorer = clustering.get("by_scorer", [])

        diff: Dict[str, Any] = {
            "type": artifact_type.value,
            "change_description": "",
            "sections_affected": [],
            "parameters": {},
        }

        if artifact_type == ArtifactType.SKILL:
            diff["change_description"] = (
                f"Optimize skill based on failure pattern: "
                f"{by_error[0].get('pattern', 'unknown') if by_error else 'general improvement'}"
            )
            diff["sections_affected"] = ["tool_selection", "output_format"]

        elif artifact_type == ArtifactType.PROMPT:
            diff["change_description"] = "Improve prompt to address output completeness issues"
            diff["sections_affected"] = ["system_prompt", "output_instructions"]

        elif artifact_type == ArtifactType.POLICY:
            diff["change_description"] = f"Update {surface} policy based on scoring feedback"
            diff["sections_affected"] = ["rules", "thresholds"]

        elif artifact_type == ArtifactType.RUBRIC:
            diff["change_description"] = "Adjust rubric weights based on judge feedback"
            diff["parameters"] = {"dimension_weights": "rebalance"}

        elif artifact_type == ArtifactType.CASE:
            diff["change_description"] = "Add regression cases from bad case pool"
            diff["parameters"] = {"action": "add_cases", "source": "bad_case_pool"}

        return diff

    def _assess_risk(self, trigger_info: Dict[str, Any], artifact_type: ArtifactType) -> RiskLevel:
        """评估变更风险等级"""
        trigger_type = trigger_info.get("trigger_type", "")

        # 安全相关 → high
        if artifact_type == ArtifactType.POLICY and "safety" in trigger_info.get("target_surface", ""):
            return RiskLevel.HIGH

        # 回退触发 → medium-high
        if trigger_type == TriggerType.REGRESSION.value:
            drop = trigger_info.get("regression_detail", {}).get("drop", 0)
            if drop > 0.2:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        # Bad Case 阈值 → medium
        if trigger_type == TriggerType.BAD_CASE_THRESHOLD.value:
            return RiskLevel.MEDIUM

        # 普通完成触发 → low-medium
        failure_rate = trigger_info.get("failure_rate", 0)
        if failure_rate > 0.5:
            return RiskLevel.HIGH
        if failure_rate > 0.3:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _build_reason(self, surface: str, trigger_info: Dict[str, Any]) -> str:
        """构建变更原因说明"""
        trigger_type = trigger_info.get("trigger_type", "unknown")
        reasons = {
            TriggerType.RUN_COMPLETED.value: f"Evaluation run completed with failures in {surface}",
            TriggerType.REGRESSION.value: "Quality trend regression detected",
            TriggerType.BAD_CASE_THRESHOLD.value: "Bad case count exceeded threshold",
            TriggerType.SCHEDULED.value: "Scheduled evolution check triggered",
        }
        base = reasons.get(trigger_type, f"Triggered by {trigger_type}")

        clustering = trigger_info.get("clustering", {})
        by_error = clustering.get("by_error", [])
        if by_error:
            base += f"; top error: {by_error[0].get('pattern', 'N/A')} (count={by_error[0].get('count', 0)})"

        return base

    def _estimate_impact(self, artifact_type: ArtifactType, artifact_id: str) -> Dict[str, Any]:
        """估算影响面"""
        return {
            "artifact_type": artifact_type.value,
            "artifact_id": artifact_id,
            "scope": "single_artifact",
            "downstream_effects": ["evaluation_scores", "agent_behavior"],
        }

    # ==================== CRUD ====================

    async def get(self, proposal_id: str) -> Optional[Proposal]:
        """获取提案详情"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one({"proposal_id": proposal_id})
        if not doc:
            return None
        return Proposal(**doc)

    async def list_proposals(
        self,
        status: Optional[str] = None,
        artifact_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Proposal]:
        """列出提案"""
        db = get_mongo_db()
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status
        if artifact_type:
            query["target_artifact_type"] = artifact_type

        cursor = db[self.COLLECTION].find(query).skip(skip).limit(limit).sort("created_at", -1)
        results = []
        async for doc in cursor:
            results.append(Proposal(**doc))
        return results

    async def update_status(self, proposal_id: str, status: ProposalStatus) -> Optional[Proposal]:
        """更新提案状态"""
        db = get_mongo_db()
        await db[self.COLLECTION].update_one(
            {"proposal_id": proposal_id},
            {"$set": {"status": status.value, "updated_at": now_tz()}},
        )
        return await self.get(proposal_id)

    async def get_stats(self) -> Dict[str, Any]:
        """获取提案统计"""
        db = get_mongo_db()
        total = await db[self.COLLECTION].count_documents({})
        by_status = {}
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        async for doc in db[self.COLLECTION].aggregate(pipeline):
            by_status[doc["_id"]] = doc["count"]
        return {"total": total, "by_status": by_status}

    async def _log_event(self, event_type: str, proposal_id: str, detail: Dict[str, Any]):
        """记录事件日志"""
        db = get_mongo_db()
        await db["evolution_event_log"].insert_one({
            "event_type": event_type,
            "proposal_id": proposal_id,
            "actor": "system",
            "detail": detail,
            "created_at": now_tz(),
        })


# 模块级单例
proposal_service = ProposalService()
