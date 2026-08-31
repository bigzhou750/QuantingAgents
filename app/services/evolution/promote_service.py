"""
Promote / Rollback / Stop 服务

负责将通过审批的候选变更写回正式 artifact 版本（promote），
或回滚到稳定版本（rollback），或紧急停止（stop）。
"""

import logging
import os
import shutil
import uuid
from typing import Optional, Dict, Any

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.evolution import (
    EvolutionReceipt,
    ProposalStatus,
    StopReason,
    ArtifactType,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class PromoteService:
    """Promote/Rollback/Stop 服务"""

    def __init__(self):
        pass

    async def promote(self, proposal_id: str, promoted_by: str = "system") -> EvolutionReceipt:
        """将候选发布为正式版本

        前置条件：提案状态必须为 APPROVED
        """
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.verification_service import verification_service
        from app.services.evolution.approval_service import approval_service
        from app.services.evolution.receipt_service import receipt_service

        # 检查提案状态
        proposal = await proposal_service.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError(f"Proposal must be approved before promote (current: {proposal.status.value})")

        # 检查 human gate
        if settings.EVOLUTION_HUMAN_GATE:
            records = await approval_service.get_records(proposal_id)
            has_approval = any(r.get("action") == "approve" for r in records)
            if not has_approval:
                raise ValueError("Human gate enabled but no approval record found")

        # 获取验证结果
        verifications = await verification_service.list_by_proposal(proposal_id)
        latest_verification = verifications[0] if verifications else None

        # 创建新版本
        content_snapshot = proposal.diff.copy()
        content_snapshot["promoted_from_proposal"] = proposal_id
        content_snapshot["promoted_by"] = promoted_by

        new_version = await artifact_registry.create_version(
            artifact_id=proposal.target_artifact_id,
            content_snapshot=content_snapshot,
            created_by=promoted_by,
        )

        # 对 Skill 类型，写入文件系统
        if proposal.target_artifact_type == ArtifactType.SKILL:
            await self._write_skill_to_disk(proposal, content_snapshot)

        # 更新提案状态
        await proposal_service.update_status(proposal_id, ProposalStatus.PROMOTED)

        # 获取审批记录
        approval_records_raw = await approval_service.get_records(proposal_id)
        from app.models.evolution import ApprovalRecord as AR
        approval_records = [AR(**r) for r in approval_records_raw]

        # 创建回执
        receipt = EvolutionReceipt(
            receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
            proposal_id=proposal_id,
            verification_id=latest_verification.verification_id if latest_verification else "",
            approval_records=approval_records,
            final_action="promoted",
            promoted_version=new_version.version,
        )
        await receipt_service.create(receipt)

        # 记录事件
        await self._log_event("proposal_promoted", proposal_id, {
            "promoted_by": promoted_by,
            "new_version": new_version.version,
            "artifact_id": proposal.target_artifact_id,
        })

        logger.info(f"[Evolution] Proposal {proposal_id} promoted to version {new_version.version}")
        return receipt

    async def rollback(self, artifact_id: str, target_version: str, rolled_back_by: str = "system") -> EvolutionReceipt:
        """回滚 artifact 到指定版本"""
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.receipt_service import receipt_service

        version = await artifact_registry.rollback(artifact_id, target_version, rolled_back_by)

        receipt = EvolutionReceipt(
            receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
            proposal_id="",
            final_action="rollback",
            promoted_version=target_version,
        )
        await receipt_service.create(receipt)

        await self._log_event("artifact_rollback", "", {
            "artifact_id": artifact_id,
            "target_version": target_version,
            "rolled_back_by": rolled_back_by,
        })

        logger.info(f"[Evolution] Artifact {artifact_id} rolled back to {target_version}")
        return receipt

    async def stop(self, proposal_id: str, reason: str = "manual", stopped_by: str = "system") -> EvolutionReceipt:
        """紧急停止提案"""
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.approval_service import approval_service
        from app.services.evolution.receipt_service import receipt_service

        # 映射原因字符串到枚举
        reason_map = {
            "budget_exceeded": StopReason.BUDGET_EXCEEDED,
            "repeated_failures": StopReason.REPEATED_FAILURES,
            "safety_regression": StopReason.SAFETY_REGRESSION,
            "gate_failure": StopReason.GATE_FAILURE,
            "manual": StopReason.MANUAL,
        }
        stop_reason = reason_map.get(reason, StopReason.MANUAL)

        # 更新提案状态
        await proposal_service.update_status(proposal_id, ProposalStatus.STOPPED)

        # 获取审批记录
        approval_records_raw = await approval_service.get_records(proposal_id)
        from app.models.evolution import ApprovalRecord as AR
        approval_records = [AR(**r) for r in approval_records_raw]

        receipt = EvolutionReceipt(
            receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
            proposal_id=proposal_id,
            approval_records=approval_records,
            final_action="stopped",
            stop_reason=stop_reason,
        )
        await receipt_service.create(receipt)

        await self._log_event("proposal_stopped", proposal_id, {
            "reason": reason,
            "stopped_by": stopped_by,
        })

        logger.info(f"[Evolution] Proposal {proposal_id} stopped: {reason}")
        return receipt

    async def _write_skill_to_disk(self, proposal, content_snapshot: Dict[str, Any]):
        """将 Skill artifact 写入 USER_SKILLS_DIR"""
        try:
            from pathlib import Path
            skill_name = proposal.target_artifact_id.replace("art_skill_", "")
            user_skills_dir = Path.home() / ".vibe-trading" / "skills" / "user"
            skill_dir = user_skills_dir / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)

            content = content_snapshot.get("content", "")
            if not content and content_snapshot.get("change_description"):
                # 如果没有完整内容，只写变更描述
                content = f"# {skill_name}\n\n## Evolution Update\n{content_snapshot['change_description']}\n"

            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(content, encoding="utf-8")
            logger.info(f"[Evolution] Wrote skill to {skill_file}")
        except Exception as e:
            logger.warning(f"[Evolution] Failed to write skill to disk: {e}")

    async def _log_event(self, event_type: str, proposal_id: str, detail: Dict[str, Any]):
        """记录事件日志"""
        db = get_mongo_db()
        await db["evolution_event_log"].insert_one({
            "event_type": event_type,
            "proposal_id": proposal_id,
            "actor": detail.get("promoted_by", detail.get("stopped_by", detail.get("rolled_back_by", "system"))),
            "detail": detail,
            "created_at": now_tz(),
        })


# 模块级单例
promote_service = PromoteService()
