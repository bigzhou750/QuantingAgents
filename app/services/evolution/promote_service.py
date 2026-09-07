"""
Promote / Rollback / Stop 服务

负责将通过审批的候选变更 materialize 到正式 artifact 位置（promote），
或回滚到稳定版本（rollback），或紧急停止（stop）。
"""

import logging
import uuid
from typing import Optional, Dict, Any

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.evolution import (
    ApprovalRecord,
    ArtifactType,
    EvolutionReceipt,
    ProposalStatus,
    StopReason,
)
from app.services.evolution.artifact_publisher import artifact_publisher
from app.services.evolution.content_diff import validate_structured_diff
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class PromoteService:
    """Promote/Rollback/Stop 服务"""

    async def promote(
        self,
        proposal_id: str,
        promoted_by: str = "system",
        request_id: str = "",
        idempotency_key: str = "",
        environment: str = "default",
        allow_skill_regression_override: bool = False,
    ) -> EvolutionReceipt:
        """将候选发布为正式版本。

        阶段顺序：创建不可变版本 -> materialize -> 发布后 smoke test ->
        切换当前指针 -> 写回执。任一关键阶段失败时当前版本指针不前移。
        """
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.approval_service import approval_service
        from app.services.evolution.governance_service import governance_service
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.receipt_service import receipt_service
        from app.services.evolution.verification_service import verification_service

        existing_receipt = await receipt_service.get_by_idempotency_key(idempotency_key)
        if existing_receipt:
            return existing_receipt

        proposal = await proposal_service.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError(
                f"Proposal must be approved before promote (current: {proposal.status.value})"
            )

        await governance_service.acquire_proposal_lock(proposal_id)

        if settings.EVOLUTION_HUMAN_GATE:
            records = await approval_service.get_records(proposal_id)
            has_approval = any(r.get("action") == "approve" for r in records)
            if not has_approval:
                raise ValueError("Human gate enabled but no approval record found")

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

        skill_regression_group_id = ""
        skill_regression_gate: Dict[str, Any] = {}
        skill_regression_override: Dict[str, Any] = {}
        if proposal.target_artifact_type == ArtifactType.SKILL:
            (
                skill_regression_group_id,
                skill_regression_gate,
                skill_regression_override,
            ) = self._resolve_skill_regression_gate(
                latest_verification.comparison_result or {},
                required=settings.EVOLUTION_SKILL_REGRESSION_REQUIRED,
                override_allowed=settings.EVOLUTION_SKILL_REGRESSION_OVERRIDE_ALLOWED,
                allow_override=allow_skill_regression_override,
                promoted_by=promoted_by,
            )
        content_diff_status = proposal.content_diff_status if isinstance(proposal.content_diff_status, str) else "complete"
        if content_diff_status == "legacy_incomplete":
            raise ValueError("Proposal content diff is incomplete; regenerate candidate before promote")
        structured_diff = proposal.structured_diff if isinstance(proposal.structured_diff, dict) else {}
        if structured_diff:
            content_validation = validate_structured_diff(structured_diff)
            if not content_validation["passed"]:
                raise ValueError(
                    "candidate content diff validation failed: "
                    + "; ".join(content_validation["errors"])
                )

        registry_entry = await artifact_registry.get_registry_entry(proposal.target_artifact_id)
        if not registry_entry:
            raise ValueError(f"Artifact {proposal.target_artifact_id} is not registered")
        current_baseline_version = await artifact_registry.get_current_version(
            proposal.target_artifact_id,
            environment=environment,
        )
        if (
            proposal.baseline_artifact_version
            and current_baseline_version
            and current_baseline_version.version != proposal.baseline_artifact_version
        ):
            raise ValueError(
                "Artifact baseline version changed during verification; re-verify before promote "
                f"(proposal baseline={proposal.baseline_artifact_version}, "
                f"current={current_baseline_version.version})"
            )

        pre_smoke_test = self._run_smoke_test(proposal)
        if settings.EVOLUTION_REQUIRE_SMOKE_TEST and not pre_smoke_test["passed"]:
            raise ValueError(
                "Promote smoke test failed: " + "; ".join(pre_smoke_test["failures"])
            )

        content_snapshot = proposal.diff.copy()
        content_snapshot["promoted_from_proposal"] = proposal_id
        content_snapshot["promoted_by"] = promoted_by

        version_record = None
        switched = False
        operation_records: list[Dict[str, Any]] = []
        try:
            version_record = await artifact_registry.create_version_record(
                artifact_id=proposal.target_artifact_id,
                content_snapshot=content_snapshot,
                created_by=promoted_by,
                environment=environment,
                source_proposal_id=proposal_id,
            )
            operation_records.append({
                "phase": "version_created",
                "status": "ok",
                "version": version_record.version,
                "at": now_tz().isoformat(),
            })

            materialization = await artifact_publisher.materialize(version_record, environment)
            await get_mongo_db()[artifact_registry.COLLECTION_VERSIONS].update_one(
                {"artifact_id": proposal.target_artifact_id, "version": version_record.version},
                {"$set": {"materialization": materialization, "updated_at": now_tz()}},
            )
            operation_records.append({
                "phase": "materialized",
                "status": "ok",
                "files": materialization.get("files", []),
                "at": now_tz().isoformat(),
            })

            smoke_test_result = await self._run_promoted_smoke_test(
                version_record, environment=environment
            )
            if settings.EVOLUTION_REQUIRE_SMOKE_TEST and not smoke_test_result["passed"]:
                raise ValueError(
                    "Post-promote smoke test failed: "
                    + "; ".join(smoke_test_result.get("failures", []))
                )
            operation_records.append({
                "phase": "post_smoke_test",
                "status": "ok",
                "at": now_tz().isoformat(),
            })

            before_version = (
                current_baseline_version.version
                if current_baseline_version
                else proposal.baseline_artifact_version or registry_entry.current_version
            )
            activated = await artifact_registry.activate_version(
                artifact_id=proposal.target_artifact_id,
                version=version_record.version,
                environment=environment,
                activated_by=promoted_by,
                mode="promote",
            )
            switched = True
            operation_records.append({
                "phase": "pointer_switched",
                "status": "ok",
                "before_version": before_version,
                "after_version": activated.version,
                "environment": environment,
                "at": now_tz().isoformat(),
            })

            await proposal_service.update_status(proposal_id, ProposalStatus.PROMOTED)

            approval_records_raw = await approval_service.get_records(proposal_id)
            approval_records = [ApprovalRecord(**r) for r in approval_records_raw]

            receipt = EvolutionReceipt(
                receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
                proposal_id=proposal_id,
                verification_id=latest_verification.verification_id,
                approval_records=approval_records,
                final_action="promoted",
                promoted_version=version_record.version,
                gate_result=gate_result,
                smoke_test_result=smoke_test_result,
                baseline_artifact_version=proposal.baseline_artifact_version,
                candidate_version=version_record.version,
                artifact_id=proposal.target_artifact_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                environment=environment,
                release_status="succeeded",
                before_version=before_version,
                after_version=version_record.version,
                version_switch={
                    "before": before_version,
                    "after": version_record.version,
                    "environment": environment,
                    "switched_at": now_tz().isoformat(),
                },
                operation_records=operation_records,
                content_diff_status=content_diff_status,
                content_summary=structured_diff.get("change_description", ""),
                materialization_files=materialization.get("files", []),
                skill_regression_group_id=skill_regression_group_id,
                skill_regression_gate=skill_regression_gate,
                skill_regression_override=skill_regression_override,
            )
            await receipt_service.create(receipt)
            await get_mongo_db()[artifact_registry.COLLECTION_VERSIONS].update_one(
                {"artifact_id": proposal.target_artifact_id, "version": version_record.version},
                {"$set": {"release_receipt_id": receipt.receipt_id, "updated_at": now_tz()}},
            )
            operation_records.append({
                "phase": "receipt_created",
                "status": "ok",
                "receipt_id": receipt.receipt_id,
                "at": now_tz().isoformat(),
            })

            await self._log_event("proposal_promoted", proposal_id, {
                "promoted_by": promoted_by,
                "new_version": version_record.version,
                "artifact_id": proposal.target_artifact_id,
                "environment": environment,
            })
            try:
                await governance_service.notify("proposal_promote", {
                    "proposal_id": proposal_id,
                    "artifact_id": proposal.target_artifact_id,
                    "version": version_record.version,
                    "environment": environment,
                })
            except Exception:
                logger.warning("Failed to notify proposal promotion", exc_info=True)
            return receipt
        except Exception as exc:
            error_message = str(exc)[:500]
            operation_records.append({
                "phase": "failed",
                "status": "failed",
                "error": error_message,
                "at": now_tz().isoformat(),
            })
            if version_record:
                await artifact_registry.mark_version_failed(
                    proposal.target_artifact_id,
                    version_record.version,
                    error_message,
                )
            if switched:
                try:
                    before_version = (
                        current_baseline_version.version
                        if current_baseline_version
                        else proposal.baseline_artifact_version or registry_entry.current_version
                    )
                    await artifact_registry.activate_version(
                        artifact_id=proposal.target_artifact_id,
                        version=before_version,
                        environment=environment,
                        activated_by="promote_compensation",
                        mode="promote",
                    )
                except Exception as compensation_error:
                    logger.warning("Promote compensation switch failed", exc_info=compensation_error)
            await self._log_event("release_compensated", proposal_id, {
                "operation": "promote",
                "environment": environment,
                "error": error_message,
                "operation_records": operation_records,
            })
            raise

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

    async def _run_promoted_smoke_test(
        self,
        version,
        environment: str = "default",
    ) -> Dict[str, Any]:
        """检查已 materialize 的 active artifact 是否可以被 runtime 读取。"""
        failures = []
        snapshot = version.content_snapshot or {}
        if not snapshot:
            failures.append("active version snapshot is empty")
        if version.artifact_type == ArtifactType.SKILL:
            skill_paths = artifact_publisher.runtime_skill_paths(version.artifact_id, environment)
            skill_file = next((path for path in skill_paths if path.is_file()), None)
            if not skill_file:
                failures.append(f"active Skill file missing: {skill_paths[0]}")
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
        environment: str = "default",
    ) -> EvolutionReceipt:
        """回滚 artifact 到指定版本。

        先校验并 materialize 目标版本，成功后再切换当前指针，避免失败时正式版本漂移。
        """
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.governance_service import governance_service
        from app.services.evolution.receipt_service import receipt_service

        existing_receipt = await receipt_service.get_by_idempotency_key(idempotency_key)
        if existing_receipt:
            return existing_receipt

        version = await artifact_registry.get_version(artifact_id, target_version)
        if not version:
            raise ValueError(f"Version {target_version} not found for artifact {artifact_id}")
        version_status = getattr(version.status, "value", version.status)
        if version_status in {"pending", "failed"}:
            raise ValueError(f"Version {target_version} is not usable for rollback")

        before_version = await artifact_registry.get_current_version(artifact_id, environment)
        before_version_str = before_version.version if before_version else ""
        switched = False
        operation_records: list[Dict[str, Any]] = []
        try:
            materialization = await artifact_publisher.materialize(version, environment)
            await get_mongo_db()[artifact_registry.COLLECTION_VERSIONS].update_one(
                {"artifact_id": artifact_id, "version": target_version},
                {"$set": {"materialization": materialization, "updated_at": now_tz()}},
            )
            operation_records.append({
                "phase": "rollback_materialized",
                "status": "ok",
                "version": target_version,
                "files": materialization.get("files", []),
                "at": now_tz().isoformat(),
            })

            smoke_test_result = await self._run_promoted_smoke_test(version, environment)
            if not smoke_test_result["passed"]:
                raise ValueError(
                    "Rollback smoke test failed: "
                    + "; ".join(smoke_test_result.get("failures", []))
                )
            operation_records.append({
                "phase": "rollback_smoke_test",
                "status": "ok",
                "at": now_tz().isoformat(),
            })

            activated = await artifact_registry.activate_version(
                artifact_id=artifact_id,
                version=target_version,
                environment=environment,
                activated_by=rolled_back_by,
                mode="rollback",
            )
            switched = True
            operation_records.append({
                "phase": "rollback_pointer_switched",
                "status": "ok",
                "before_version": before_version_str,
                "after_version": activated.version,
                "at": now_tz().isoformat(),
            })

            receipt = EvolutionReceipt(
                receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
                proposal_id="",
                final_action="rollback",
                promoted_version=target_version,
                smoke_test_result=smoke_test_result,
                request_id=request_id,
                idempotency_key=idempotency_key,
                artifact_id=artifact_id,
                environment=environment,
                release_status="succeeded",
                before_version=before_version_str,
                after_version=target_version,
                version_switch={
                    "before": before_version_str,
                    "after": target_version,
                    "environment": environment,
                    "switched_at": now_tz().isoformat(),
                },
                operation_records=operation_records,
            )
            await receipt_service.create(receipt)
            await get_mongo_db()[artifact_registry.COLLECTION_VERSIONS].update_one(
                {"artifact_id": artifact_id, "version": target_version},
                {"$set": {"release_receipt_id": receipt.receipt_id, "updated_at": now_tz()}},
            )

            await self._log_event("artifact_rollback", "", {
                "artifact_id": artifact_id,
                "target_version": target_version,
                "rolled_back_by": rolled_back_by,
                "environment": environment,
                "receipt_id": receipt.receipt_id,
            })
            try:
                await governance_service.notify("artifact_rollback", {
                    "artifact_id": artifact_id,
                    "target_version": target_version,
                    "rolled_back_by": rolled_back_by,
                    "environment": environment,
                })
            except Exception:
                logger.warning("Failed to notify artifact rollback", exc_info=True)
            return receipt
        except Exception as exc:
            operation_records.append({
                "phase": "rollback_failed",
                "status": "failed",
                "error": str(exc)[:500],
                "at": now_tz().isoformat(),
            })
            if switched and before_version:
                try:
                    await artifact_registry.activate_version(
                        artifact_id=artifact_id,
                        version=before_version_str,
                        environment=environment,
                        activated_by="rollback_compensation",
                        mode="promote",
                    )
                except Exception as compensation_error:
                    logger.warning("Rollback compensation switch failed", exc_info=compensation_error)
            await self._log_event("release_compensated", "", {
                "operation": "rollback",
                "artifact_id": artifact_id,
                "target_version": target_version,
                "environment": environment,
                "error": str(exc)[:500],
                "operation_records": operation_records,
            })
            raise

    async def stop(
        self,
        proposal_id: str,
        reason: str = "manual",
        stopped_by: str = "system",
        request_id: str = "",
        idempotency_key: str = "",
    ) -> EvolutionReceipt:
        """紧急停止提案"""
        from app.services.evolution.approval_service import approval_service
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.receipt_service import receipt_service

        existing_receipt = await receipt_service.get_by_idempotency_key(idempotency_key)
        if existing_receipt:
            return existing_receipt

        reason_map = {
            "budget_exceeded": StopReason.BUDGET_EXCEEDED,
            "repeated_failures": StopReason.REPEATED_FAILURES,
            "safety_regression": StopReason.SAFETY_REGRESSION,
            "gate_failure": StopReason.GATE_FAILURE,
            "manual": StopReason.MANUAL,
        }
        stop_reason = reason_map.get(reason, StopReason.MANUAL)

        await proposal_service.update_status(proposal_id, ProposalStatus.STOPPED)

        approval_records_raw = await approval_service.get_records(proposal_id)
        approval_records = [ApprovalRecord(**r) for r in approval_records_raw]

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

    @staticmethod
    def _resolve_skill_regression_gate(
        comparison_result: Dict[str, Any],
        *,
        required: bool,
        override_allowed: bool,
        allow_override: bool,
        promoted_by: str,
    ) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
        group_id = str(comparison_result.get("skill_regression_group_id", ""))
        gate = dict(comparison_result.get("skill_regression_gate") or {})
        override: Dict[str, Any] = {}
        if required and not gate.get("passed", False):
            if not (override_allowed and allow_override):
                raise ValueError(
                    "Skill regression gate failed or is missing; promote is blocked"
                )
            override = {
                "allowed": True,
                "reason": "管理员显式覆盖 Skill 回归门禁",
                "overridden_by": promoted_by,
                "overridden_at": now_tz().isoformat(),
            }
        return group_id, gate, override

    async def _write_skill_version_to_disk(self, version, skills_dir: Any = None) -> None:
        """将目标 Skill 版本恢复到可运行用户 Skill 路径。"""
        from pathlib import Path
        skill_name = version.artifact_id.replace("art_skill_", "")
        if skills_dir is None:
            root = artifact_publisher.skill_user_dir()
        else:
            root = Path(skills_dir)
        skill_file = root / skill_name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        content = (version.content_snapshot or {}).get("content", "")
        if not content:
            raise ValueError("rollback Skill content is empty")
        skill_file.write_text(content, encoding="utf-8")
        await self._invalidate_skill_cache(version.artifact_id)

    async def _write_skill_to_disk(
        self,
        proposal,
        content_snapshot: Dict[str, Any],
        skills_dir: Any = None,
    ) -> None:
        """兼容入口：直接写一个 Skill 目录。"""
        from pathlib import Path
        skill_name = proposal.target_artifact_id.replace("art_skill_", "")
        if skills_dir is None:
            user_skills_dir = artifact_publisher.skill_user_dir()
        else:
            user_skills_dir = Path(skills_dir)
        skill_dir = user_skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = content_snapshot.get("content", "")
        if not content and content_snapshot.get("change_description"):
            content = f"# {skill_name}\n\n## Evolution Update\n{content_snapshot['change_description']}\n"
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(content, encoding="utf-8")
        await self._invalidate_skill_cache(proposal.target_artifact_id)
        logger.info(f"[Evolution] Wrote skill to {skill_file}")

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
