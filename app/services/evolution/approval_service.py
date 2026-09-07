"""
审批服务

管理候选提案的批准、拒绝和评论流程，记录完整审计轨迹。
"""

import logging
from typing import List, Dict, Any

from app.core.database import get_mongo_db
from app.models.evolution import (
    ApprovalRecord,
    ApprovalAction,
    ProposalStatus,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class ApprovalService:
    """审批服务"""

    COLLECTION = "evolution_approvals"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务和索引"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("proposal_id")
        await db[self.COLLECTION].create_index("action")
        await db[self.COLLECTION].create_index("timestamp")
        self._initialized = True
        logger.info("ApprovalService initialized")

    async def approve(
        self,
        proposal_id: str,
        auditor: str,
        comment: str = "",
        request_id: str = "",
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """批准提案"""
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.verification_service import verification_service

        proposal = await proposal_service.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.VERIFIED:
            raise ValueError(
                f"Proposal must be verified before approval (current: {proposal.status.value})"
            )
        from app.services.evolution.artifact_registry import artifact_registry
        current_baseline = await artifact_registry.get_current_version(proposal.target_artifact_id)
        if (
            proposal.baseline_artifact_version
            and current_baseline
            and current_baseline.version != proposal.baseline_artifact_version
        ):
            raise ValueError(
                "baseline drift detected; re-verify before approval "
                f"(proposal baseline={proposal.baseline_artifact_version}, "
                f"current={current_baseline.version})"
            )
        verifications = await verification_service.list_by_proposal(proposal_id)
        latest = verifications[0] if verifications else None
        if not latest or latest.status != "completed":
            raise ValueError("Proposal has no completed verification")
        gate = latest.gate_result or latest.comparison_result.get("gate", {})
        if gate and gate.get("passed") is False:
            raise ValueError("Proposal verification gate did not pass")

        record = ApprovalRecord(
            reviewer=auditor,
            action=ApprovalAction.APPROVE,
            comment=comment,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        record_dict = record.model_dump()

        db = get_mongo_db()
        if idempotency_key:
            existing = await db[self.COLLECTION].find_one({"idempotency_key": idempotency_key})
            if existing:
                existing.pop("_id", None)
                return existing
        await db[self.COLLECTION].insert_one({
            "proposal_id": proposal_id,
            **record_dict,
        })

        # 更新提案状态
        await proposal_service.update_status(proposal_id, ProposalStatus.APPROVED)

        # 记录事件
        await self._log_event("proposal_approved", proposal_id, {
            "auditor": auditor,
            "comment": comment,
        })

        logger.info(f"[Evolution] Proposal {proposal_id} approved by {auditor}")
        return record_dict

    async def reject(
        self,
        proposal_id: str,
        auditor: str,
        comment: str = "",
        request_id: str = "",
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """拒绝提案"""
        from app.services.evolution.proposal_service import proposal_service

        proposal = await proposal_service.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.VERIFIED:
            raise ValueError(
                f"Proposal cannot be rejected from current status: {proposal.status.value}"
            )

        record = ApprovalRecord(
            reviewer=auditor,
            action=ApprovalAction.REJECT,
            comment=comment,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        record_dict = record.model_dump()

        db = get_mongo_db()
        if idempotency_key:
            existing = await db[self.COLLECTION].find_one({"idempotency_key": idempotency_key})
            if existing:
                existing.pop("_id", None)
                return existing
        await db[self.COLLECTION].insert_one({
            "proposal_id": proposal_id,
            **record_dict,
        })

        await proposal_service.update_status(proposal_id, ProposalStatus.REJECTED)

        await self._log_event("proposal_rejected", proposal_id, {
            "auditor": auditor,
            "comment": comment,
        })

        logger.info(f"[Evolution] Proposal {proposal_id} rejected by {auditor}")
        return record_dict

    async def comment(
        self, proposal_id: str, auditor: str, comment: str,
        request_id: str = "",
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """添加评论（不改变状态）"""
        record = ApprovalRecord(
            reviewer=auditor,
            action=ApprovalAction.COMMENT,
            comment=comment,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        record_dict = record.model_dump()

        db = get_mongo_db()
        if idempotency_key:
            existing = await db[self.COLLECTION].find_one({"idempotency_key": idempotency_key})
            if existing:
                existing.pop("_id", None)
                return existing
        await db[self.COLLECTION].insert_one({
            "proposal_id": proposal_id,
            **record_dict,
        })

        await self._log_event("proposal_commented", proposal_id, {
            "auditor": auditor,
            "comment": comment,
        })

        return record_dict

    async def get_records(self, proposal_id: str) -> List[Dict[str, Any]]:
        """获取提案的所有审批记录"""
        db = get_mongo_db()
        cursor = db[self.COLLECTION].find({"proposal_id": proposal_id}).sort("timestamp", 1)
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
        return results

    async def _log_event(self, event_type: str, proposal_id: str, detail: Dict[str, Any]):
        """记录事件日志"""
        db = get_mongo_db()
        await db["evolution_event_log"].insert_one({
            "event_type": event_type,
            "proposal_id": proposal_id,
            "actor": detail.get("auditor", "system"),
            "detail": detail,
            "created_at": now_tz(),
        })


# 模块级单例
approval_service = ApprovalService()
