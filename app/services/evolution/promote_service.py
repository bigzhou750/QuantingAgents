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

    async def promote(
        self,
        proposal_id: str,
        promoted_by: str = "system",
        request_id: str = "",
        idempotency_key: str = "",
    ) -> EvolutionReceipt:
        """将候选发布为正式版本

        前置条件：提案状态必须为 APPROVED
        """
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.verification_service import verification_service
        from app.services.evolution.approval_service import approval_service
        from app.services.evolution.receipt_service import receipt_service

        existing_receipt = await receipt_service.get_by_idempotency_key(idempotency_key)
        if existing_receipt:
            return existing_receipt

        # 检查提案状态
        proposal = await proposal_service.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError(f"Proposal must be approved before promote (current: {proposal.status.value})")

        from app.services.evolution.governance_service import governance_service
        await governance_service.acquire_proposal_lock(proposal_id)

        # 检查 human gate
        if settings.EVOLUTION_HUMAN_GATE:
            records = await approval_service.get_records(proposal_id)
            has_approval = any(r.get("action") == "approve" for r in records)
            if not has_approval:
                raise ValueError("Human gate enabled but no approval record found")

        # 获取验证结果
        verifications = await verification_service.list_by_proposal(proposal_id)
        latest_verification = verifications[0] if verifications else None
        if not latest_verification or latest_verification.status != "completed":
            raise ValueError("Proposal must have a completed verification before promote")
        if latest_verification.cleanup_status != "cleaned":
            raise ValueError("Verification sandbox cleanup has not completed successfully")

        gate_result = latest_verification.gate_result or {}
        if not gate_result:
            gate_result = latest_verification.comparison_result.get("gate", {})
        if gate_result.get("passed") is False:
            raise ValueError("Verification gate failed; promote is blocked")

        registry_entry = await artifact_registry.get_registry_entry(proposal.target_artifact_id)
        if not registry_entry:
            raise ValueError(f"Artifact {proposal.target_artifact_id} is not registered")
        if proposal.baseline_artifact_version and registry_entry.current_version != proposal.baseline_artifact_version:
            raise ValueError(
                "Artifact baseline version changed during verification; re-verify before promote"
            )

        pre_smoke_test = self._run_smoke_test(proposal)
        if settings.EVOLUTION_REQUIRE_SMOKE_TEST and not pre_smoke_test["passed"]:
            raise ValueError(
                "Promote smoke test failed: "
                + "; ".join(pre_smoke_test["failures"])
            )

        # 创建新版本
        content_snapshot = proposal.diff.copy()
        content_snapshot["promoted_from_proposal"] = proposal_id
        content_snapshot["promoted_by"] = promoted_by

        new_version = await artifact_registry.create_version(
            artifact_id=proposal.target_artifact_id,
            content_snapshot=content_snapshot,
            created_by=promoted_by,
        )

        # 写正式版本、smoke test、状态和回执作为一个可补偿单元。
        try:
            # 对 Skill 类型，写入文件系统
            if proposal.target_artifact_type == ArtifactType.SKILL:
                await self._write_skill_to_disk(proposal, content_snapshot)

            smoke_test_result = await self._run_promoted_smoke_test(new_version)
            if settings.EVOLUTION_REQUIRE_SMOKE_TEST and not smoke_test_result["passed"]:
                raise ValueError(
                    "Post-promote smoke test failed: "
                    + "; ".join(smoke_test_result.get("failures", []))
                )

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
                gate_result=gate_result,
                smoke_test_result=smoke_test_result,
                baseline_artifact_version=proposal.baseline_artifact_version,
                candidate_version=new_version.version,
                artifact_id=proposal.target_artifact_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
            )
            await receipt_service.create(receipt)

            # 记录事件
            await self._log_event("proposal_promoted", proposal_id, {
                "promoted_by": promoted_by,
                "new_version": new_version.version,
                "artifact_id": proposal.target_artifact_id,
            })
            try:
                await governance_service.notify("proposal_promote", {
                    "proposal_id": proposal_id,
                    "artifact_id": proposal.target_artifact_id,
                    "version": new_version.version,
                })
            except Exception:
                logger.warning("Failed to notify proposal promotion", exc_info=True)
        except Exception:
            try:
                await artifact_registry.rollback(
                    proposal.target_artifact_id,
                    proposal.baseline_artifact_version,
                    rolled_back_by="promote_compensation",
                )
            except Exception:
                logger.warning("Promote compensation rollback failed", exc_info=True)
            raise

        logger.info(f"[Evolution] Proposal {proposal_id} promoted to version {new_version.version}")
        return receipt

    @staticmethod
    def _run_smoke_test(proposal) -> Dict[str, Any]:
        """在写正式版本前验证候选内容具备最小可加载结构。"""
        failures = []
        diff = proposal.diff or {}
        if not diff.get("type"):
            failures.append("missing artifact type")
        if not diff.get("change_description") and not diff.get("candidate_snapshot"):
            failures.append("candidate content is empty")
        sections = diff.get("sections_affected", [])
        if not isinstance(sections, list):
            failures.append("sections_affected must be a list")
        return {
            "passed": not failures,
            "failures": failures,
            "checked_at": now_tz().isoformat(),
        }

    async def _run_promoted_smoke_test(self, version) -> Dict[str, Any]:
        """检查已写入的 active artifact 是否可以被 runtime 读取。"""
        failures = []
        snapshot = version.content_snapshot or {}
        if not snapshot:
            failures.append("active version snapshot is empty")
        if version.artifact_type == ArtifactType.SKILL:
            from pathlib import Path
            skill_name = version.artifact_id.replace("art_skill_", "")
            skill_file = Path.home() / ".vibe-trading" / "skills" / "user" / skill_name / "SKILL.md"
            if not skill_file.is_file():
                failures.append(f"active Skill file missing: {skill_file}")
            elif not skill_file.read_text(encoding="utf-8").strip():
                failures.append("active Skill file is empty")
        return {
            "passed": not failures,
            "failures": failures,
            "checked_at": now_tz().isoformat(),
        }

    async def rollback(
        self,
        artifact_id: str,
        target_version: str,
        rolled_back_by: str = "system",
        request_id: str = "",
        idempotency_key: str = "",
    ) -> EvolutionReceipt:
        """回滚 artifact 到指定版本"""
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.receipt_service import receipt_service

        from app.services.evolution.receipt_service import receipt_service
        existing_receipt = await receipt_service.get_by_idempotency_key(idempotency_key)
        if existing_receipt:
            return existing_receipt

        version = await artifact_registry.rollback(artifact_id, target_version, rolled_back_by)

        if version.artifact_type == ArtifactType.SKILL:
            await self._write_skill_version_to_disk(version)
        smoke_test_result = {
            "passed": bool(version.content_snapshot),
            "checked_at": now_tz().isoformat(),
        }
        if not smoke_test_result["passed"]:
            raise ValueError("rollback target has empty content snapshot")

        receipt = EvolutionReceipt(
            receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
            proposal_id="",
            final_action="rollback",
            promoted_version=target_version,
            smoke_test_result=smoke_test_result,
            request_id=request_id,
            idempotency_key=idempotency_key,
            artifact_id=artifact_id,
        )
        await receipt_service.create(receipt)

        await self._log_event("artifact_rollback", "", {
            "artifact_id": artifact_id,
            "target_version": target_version,
            "rolled_back_by": rolled_back_by,
        })
        from app.services.evolution.governance_service import governance_service
        try:
            await governance_service.notify("artifact_rollback", {
                "artifact_id": artifact_id,
                "target_version": target_version,
                "rolled_back_by": rolled_back_by,
            })
        except Exception:
            logger.warning("Failed to notify artifact rollback", exc_info=True)

        logger.info(f"[Evolution] Artifact {artifact_id} rolled back to {target_version}")
        return receipt

    async def _write_skill_version_to_disk(self, version, skills_dir: Any = None) -> None:
        """将目标 Skill 版本恢复到正式用户 Skill 路径。"""
        from pathlib import Path
        skill_name = version.artifact_id.replace("art_skill_", "")
        if skills_dir is None:
            root = Path.home() / ".vibe-trading" / "skills" / "user"
        else:
            root = Path(skills_dir)
        skill_file = root / skill_name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        content = (version.content_snapshot or {}).get("content", "")
        if not content:
            raise ValueError("rollback Skill content is empty")
        skill_file.write_text(content, encoding="utf-8")
        await self._invalidate_skill_cache(version.artifact_id)

    async def stop(
        self,
        proposal_id: str,
        reason: str = "manual",
        stopped_by: str = "system",
        request_id: str = "",
        idempotency_key: str = "",
    ) -> EvolutionReceipt:
        """紧急停止提案"""
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.approval_service import approval_service
        from app.services.evolution.receipt_service import receipt_service

        existing_receipt = await receipt_service.get_by_idempotency_key(idempotency_key)
        if existing_receipt:
            return existing_receipt

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
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        await receipt_service.create(receipt)

        await self._log_event("proposal_stopped", proposal_id, {
            "reason": reason,
            "stopped_by": stopped_by,
        })

        logger.info(f"[Evolution] Proposal {proposal_id} stopped: {reason}")
        return receipt

    async def _write_skill_to_disk(
        self, proposal, content_snapshot: Dict[str, Any], skills_dir: Any = None
    ):
        """将 Skill artifact 写入 USER_SKILLS_DIR"""
        try:
            from pathlib import Path
            skill_name = proposal.target_artifact_id.replace("art_skill_", "")
            if skills_dir is None:
                user_skills_dir = Path.home() / ".vibe-trading" / "skills" / "user"
            else:
                user_skills_dir = Path(skills_dir)
            skill_dir = user_skills_dir / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)

            content = content_snapshot.get("content", "")
            if not content and content_snapshot.get("change_description"):
                # 如果没有完整内容，只写变更描述
                content = f"# {skill_name}\n\n## Evolution Update\n{content_snapshot['change_description']}\n"

            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(content, encoding="utf-8")
            await self._invalidate_skill_cache(proposal.target_artifact_id)
            logger.info(f"[Evolution] Wrote skill to {skill_file}")
        except Exception as e:
            logger.warning(f"[Evolution] Failed to write skill to disk: {e}")

    @staticmethod
    async def _invalidate_skill_cache(artifact_id: str) -> None:
        """使 Skill runtime cache 失效；Redis 不可用时静默降级。"""
        try:
            from app.core.database import get_redis_client
            redis = get_redis_client()
            await redis.delete(
                f"evolution:skill:{artifact_id}",
                f"evolution:skill:{artifact_id}:content",
            )
        except Exception:
            logger.debug("Skill runtime cache invalidation skipped", exc_info=True)

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
