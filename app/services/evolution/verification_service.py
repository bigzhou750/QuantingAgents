"""
候选验证服务

负责创建 sandbox 环境、运行候选验证 run、对比基线和候选指标。
使用临时文件覆盖机制实现 artifact 隔离。
"""

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.evolution import (
    VerificationRun,
    ProposalStatus,
    ArtifactType,
)
from app.utils.timezone import now_tz
from app.services.evolution.content_diff import validate_structured_diff

logger = logging.getLogger(__name__)


class VerificationService:
    """候选验证服务"""

    COLLECTION = "evolution_verifications"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务和索引"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("verification_id", unique=True)
        await db[self.COLLECTION].create_index("proposal_id")
        await db[self.COLLECTION].create_index("status")
        self._initialized = True
        logger.info("VerificationService initialized")

    async def run_verification(self, proposal_id: str) -> VerificationRun:
        """执行候选验证

        1. 加载提案和目标 artifact
        2. 创建 sandbox 并写入候选内容
        3. 创建并运行候选 eval run
        4. 对比基线和候选指标
        5. 清理 sandbox
        """
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.governance_service import governance_service
        from app.models.evolution import StopReason
        from app.services.eval.runner_service import runner_service
        from app.services.eval.metrics_service import metrics_service

        # 加载提案
        proposal = await proposal_service.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        structured_diff = proposal.structured_diff if isinstance(proposal.structured_diff, dict) else {}
        if structured_diff:
            content_validation = validate_structured_diff(structured_diff)
            if not content_validation["passed"]:
                raise ValueError(
                    "candidate content diff validation failed: "
                    + "; ".join(content_validation["errors"])
                )

        current_baseline = await artifact_registry.get_current_version(proposal.target_artifact_id)
        if (
            proposal.baseline_artifact_version
            and current_baseline
            and current_baseline.version != proposal.baseline_artifact_version
        ):
            raise ValueError(
                "baseline drift detected; proposal must be regenerated or re-verified "
                f"(proposal baseline={proposal.baseline_artifact_version}, "
                f"current={current_baseline.version})"
            )

        try:
            await governance_service.assert_verification_budget()
        except ValueError as budget_error:
            await governance_service.stop(
                proposal_id,
                StopReason.BUDGET_EXCEEDED,
                {"error": str(budget_error)},
            )
            raise
        try:
            await governance_service.assert_no_repeated_failure(
                proposal.fingerprint, proposal.target_artifact_id, proposal_id
            )
        except ValueError as repeat_error:
            raise

        # 更新状态为 verifying
        await proposal_service.update_status(proposal_id, ProposalStatus.VERIFYING)

        verification_id = f"vrf_{uuid.uuid4().hex[:12]}"
        overlay_id = f"overlay_{uuid.uuid4().hex[:12]}"
        sandbox_path = ""
        overlay_manifest: Dict[str, Any] = {}
        verification_record: Optional[VerificationRun] = None

        try:
            # 基线以提案创建时冻结的版本为准；current_baseline 仅用于漂移校验。
            current_version = current_baseline
            baseline_version = self._frozen_baseline(proposal, current_baseline)

            # 创建 sandbox
            sandbox_path = self._create_sandbox(proposal, current_version)
            overlay_manifest = {
                "overlay_id": overlay_id,
                "proposal_id": proposal_id,
                "artifact_id": proposal.target_artifact_id,
                "artifact_type": proposal.target_artifact_type.value,
                "baseline_version": baseline_version,
                "candidate_version": proposal.candidate_version or "candidate",
                "sandbox_path": sandbox_path,
                "dataset_version": "",
                "created_at": now_tz().isoformat(),
            }

            # 确定 dataset_id（从 trigger run 获取）
            db = get_mongo_db()
            trigger_run = await db["eval_runs"].find_one({"run_id": proposal.trigger_run_id})
            dataset_id = trigger_run.get("dataset_id", "") if trigger_run else ""
            dataset_version = trigger_run.get("dataset_version") if trigger_run else None
            overlay_manifest["dataset_version"] = dataset_version or ""

            await db[proposal_service.COLLECTION].update_one(
                {"proposal_id": proposal_id},
                {"$set": {
                    "overlay_id": overlay_id,
                    "baseline_artifact_version": baseline_version,
                    "candidate_version": overlay_manifest["candidate_version"],
                    "updated_at": now_tz(),
                }},
            )

            if not dataset_id:
                raise ValueError(f"Cannot determine dataset_id from trigger run {proposal.trigger_run_id}")

            # 创建候选验证 run
            candidate_run = await runner_service.create_run(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                num_trials=max(trigger_run.get("num_trials_per_case", 1), 1) if trigger_run else 1,
                config={
                    "evolution_proposal_id": proposal_id,
                    "sandbox_path": sandbox_path,
                    "artifact_override": proposal.target_artifact_id,
                    "overlay_id": overlay_id,
                    "baseline_artifact_version": overlay_manifest["baseline_version"],
                    "candidate_version": overlay_manifest["candidate_version"],
                    "overlay_dataset_version": dataset_version or "",
                    "split": "validation",
                },
                created_by="evolution_verify",
            )
            candidate_run_id = candidate_run.get("run_id", "")

            # 启动候选 run
            await runner_service.start_run(candidate_run_id)

            # 等待完成（轮询，最多等 10 分钟）
            completed = False
            for _ in range(120):  # 120 * 5s = 600s
                run_doc = await runner_service.get_run(candidate_run_id)
                status = run_doc.get("status", "")
                if status in ("completed", "failed", "cancelled"):
                    completed = True
                    break
                await asyncio.sleep(5)

            if not completed:
                raise ValueError(f"Verification run {candidate_run_id} did not complete within timeout")

            skill_regression_group_id = ""
            if proposal.target_artifact_type == ArtifactType.SKILL:
                from app.services.eval.skill_regression_service import skill_regression_service

                regression_group = await skill_regression_service.create_group(
                    proposal.trigger_run_id,
                    candidate_run_id,
                    created_by="evolution_verify",
                )
                regression_group = await skill_regression_service.evaluate_gate(
                    regression_group.group_id
                )
                skill_regression_group_id = regression_group.group_id

            # 计算对比结果
            comparison = await self._compute_comparison(
                proposal.trigger_run_id,
                candidate_run_id,
                metrics_service,
                skill_regression_group_id=skill_regression_group_id,
            )

            # 保存验证记录
            verification = VerificationRun(
                verification_id=verification_id,
                proposal_id=proposal_id,
                baseline_run_id=proposal.trigger_run_id,
                candidate_run_id=candidate_run_id,
                baseline_artifact_version=baseline_version,
                sandbox_path=sandbox_path,
                overlay_id=overlay_id,
                overlay_manifest=overlay_manifest,
                comparison_result=comparison,
                gate_result=comparison.get("gate", {}),
                status="completed",
                completed_at=now_tz(),
            )
            verification_record = verification
            await db[self.COLLECTION].insert_one(verification.model_dump(by_alias=True, exclude={"id"}))

            # Gate 失败时保留完整验证记录，但禁止进入人工审批。
            if not (comparison.get("gate") or {}).get("passed", False):
                await governance_service.stop(
                    proposal_id,
                    StopReason.GATE_FAILURE,
                    comparison.get("gate", {}),
                )
            else:
                await proposal_service.update_status(proposal_id, ProposalStatus.VERIFIED)

            # 清理事件日志
            await self._log_event("verification_completed", proposal_id, {
                "verification_id": verification_id,
                "baseline_run": proposal.trigger_run_id,
                "candidate_run": candidate_run_id,
                "content_diff_status": proposal.content_diff_status,
            })
            try:
                await governance_service.notify("verification_completed", {
                    "proposal_id": proposal_id,
                    "verification_id": verification_id,
                    "gate_passed": (comparison.get("gate") or {}).get("passed", False),
                })
            except Exception:
                logger.warning("Failed to notify verification completion", exc_info=True)

            return verification

        except Exception as e:
            logger.error(f"[Evolution] Verification failed for {proposal_id}: {e}")
            await proposal_service.update_status(proposal_id, ProposalStatus.DRAFT)
            try:
                await governance_service.notify("verification_failed", {
                    "proposal_id": proposal_id,
                    "verification_id": verification_id,
                    "error": str(e)[:500],
                })
            except Exception:
                logger.warning("Failed to notify verification failure", exc_info=True)

            # 保存失败的验证记录
            db = get_mongo_db()
            failed_verification = VerificationRun(
                verification_id=verification_id,
                proposal_id=proposal_id,
                status="failed",
                sandbox_path=sandbox_path,
                overlay_id=overlay_id,
                overlay_manifest=overlay_manifest,
                cleanup_status="failed",
                comparison_result={"error": str(e)},
                completed_at=now_tz(),
            )
            await db[self.COLLECTION].insert_one(failed_verification.model_dump(by_alias=True, exclude={"id"}))
            raise

        finally:
            # 清理 sandbox
            if sandbox_path and os.path.exists(sandbox_path):
                try:
                    shutil.rmtree(sandbox_path)
                    cleanup_status = "cleaned"
                    if verification_record:
                        verification_record.cleanup_status = cleanup_status
                    await get_mongo_db()[self.COLLECTION].update_one(
                        {"verification_id": verification_id},
                        {"$set": {"cleanup_status": cleanup_status}},
                    )
                    logger.info(f"[Evolution] Cleaned up sandbox: {sandbox_path}")
                except Exception as cleanup_err:
                    if verification_record:
                        verification_record.cleanup_status = "failed"
                    try:
                        await get_mongo_db()[self.COLLECTION].update_one(
                            {"verification_id": verification_id},
                            {"$set": {"cleanup_status": "failed", "status": "cleanup_failed"}},
                        )
                    except Exception:
                        logger.warning("Failed to persist sandbox cleanup failure", exc_info=True)
                    logger.warning(f"[Evolution] Sandbox cleanup failed: {cleanup_err}")

    def _create_sandbox(self, proposal, current_version) -> str:
        """创建 sandbox 临时目录并写入候选 artifact"""
        sandbox_dir = tempfile.mkdtemp(prefix=f"evo_{proposal.proposal_id}_")

        if proposal.target_artifact_type == ArtifactType.SKILL:
            # Skill: 写入 SKILL.md 到 sandbox/skills/{skill_name}/SKILL.md
            skill_name = proposal.target_artifact_id.replace("art_skill_", "")
            skill_dir = os.path.join(sandbox_dir, "skills", skill_name)
            os.makedirs(skill_dir, exist_ok=True)

            # 获取当前内容或空模板
            current_content = ""
            if current_version and current_version.content_snapshot:
                current_content = current_version.content_snapshot.get("content", "")

            # 应用候选 diff
            candidate_content = self._apply_diff_to_content(
                current_content, proposal.diff
            )
            with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(candidate_content)

        elif proposal.target_artifact_type in (ArtifactType.PROMPT, ArtifactType.POLICY, ArtifactType.RUBRIC):
            # 非文件类 artifact: 写入 JSON 快照
            config_dir = os.path.join(sandbox_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            import json
            snapshot = proposal.diff.get("candidate_snapshot", {})
            with open(os.path.join(config_dir, f"{proposal.target_artifact_id}.json"), "w") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

        logger.info(f"[Evolution] Created sandbox at {sandbox_dir} for proposal {proposal.proposal_id}")
        return sandbox_dir

    @staticmethod
    def _frozen_baseline(proposal, current_baseline) -> str:
        """返回提案创建时冻结的基线版本，而不是运行时当前版本。"""
        if proposal.baseline_artifact_version:
            return proposal.baseline_artifact_version
        return current_baseline.version if current_baseline else ""

    def _apply_diff_to_content(self, current_content: str, diff: Dict[str, Any]) -> str:
        """将候选 diff 应用到当前内容上

        简化实现：在末尾追加变更说明段落。
        生产级应使用结构化 markdown section editing。
        """
        change_desc = diff.get("change_description", "Automated evolution update")
        sections = diff.get("sections_affected", [])

        addition = f"\n\n## Evolution Update\n<!-- Auto-generated by self-evolution -->\n"
        addition += f"Change: {change_desc}\n"
        if sections:
            addition += f"Sections affected: {', '.join(sections)}\n"

        return current_content + addition

    async def _compute_comparison(
        self,
        baseline_run_id: str,
        candidate_run_id: str,
        metrics_service,
        skill_regression_group_id: str = "",
    ) -> Dict[str, Any]:
        """计算基线与候选的指标对比"""
        try:
            comparison = await metrics_service.compare_runs([baseline_run_id, candidate_run_id])

            # 补充 pass@k 和 pass^k
            baseline_pass_at_k = await metrics_service.compute_pass_at_k(baseline_run_id, k=3)
            candidate_pass_at_k = await metrics_service.compute_pass_at_k(candidate_run_id, k=3)

            # 补充评分聚合
            baseline_scores = await metrics_service.get_score_aggregation(baseline_run_id)
            candidate_scores = await metrics_service.get_score_aggregation(candidate_run_id)

            result = {
                "comparison": comparison,
                "pass_at_k": {
                    "baseline": baseline_pass_at_k,
                    "candidate": candidate_pass_at_k,
                },
                "score_aggregation": {
                    "baseline": baseline_scores,
                    "candidate": candidate_scores,
                },
                "new_regressions": [],
            }

            # 检测新增 regression
            if isinstance(comparison, dict):
                runs_data = comparison.get("runs", [])
                if len(runs_data) >= 2:
                    b_rate = runs_data[0].get("success_rate", 0)
                    c_rate = runs_data[1].get("success_rate", 0)
                    if c_rate < b_rate:
                        result["regression_detected"] = True
                        result["regression_delta"] = round(b_rate - c_rate, 4)
                    else:
                        result["regression_detected"] = False
                        result["regression_delta"] = round(c_rate - b_rate, 4)

            runs_data = comparison.get("runs", []) if isinstance(comparison, dict) else []
            checks = []
            if len(runs_data) >= 2:
                baseline_metrics, candidate_metrics = runs_data[0], runs_data[1]
                success_ok = candidate_metrics.get("success_rate", 0) >= baseline_metrics.get("success_rate", 0)
                checks.append({"name": "success_rate", "passed": success_ok})
                baseline_latency = (baseline_metrics.get("latency") or {}).get("mean_ms", 0)
                candidate_latency = (candidate_metrics.get("latency") or {}).get("mean_ms", 0)
                latency_ok = not baseline_latency or candidate_latency <= baseline_latency * 1.2
                checks.append({"name": "latency_budget", "passed": latency_ok})
                baseline_cost = (baseline_metrics.get("cost") or {}).get("total_usd", 0)
                candidate_cost = (candidate_metrics.get("cost") or {}).get("total_usd", 0)
                cost_ok = not baseline_cost or candidate_cost <= baseline_cost * 1.2
                checks.append({"name": "cost_budget", "passed": cost_ok})

            baseline_scores = baseline_scores.get("scores", {})
            candidate_scores = candidate_scores.get("scores", {})
            for scorer_name in ("safety", "evidence_quality", "trajectory"):
                if scorer_name in baseline_scores and scorer_name in candidate_scores:
                    checks.append({
                        "name": scorer_name,
                        "passed": candidate_scores[scorer_name].get("avg_score", 0)
                        >= baseline_scores[scorer_name].get("avg_score", 0),
                    })
            result["gate"] = {
                "passed": bool(checks) and all(check["passed"] for check in checks),
                "checks": checks,
                "evaluated_at": now_tz().isoformat(),
            }

            if skill_regression_group_id:
                from app.services.eval.skill_regression_service import skill_regression_service

                group = await skill_regression_service.get_group(skill_regression_group_id)
                if group:
                    new_regressions = [
                        delta.model_dump(by_alias=True)
                        for delta in group.per_case_deltas
                        if delta.regressed
                    ]
                    result["new_regressions"] = new_regressions
                    if group.gate_result:
                        result["skill_regression_group_id"] = group.group_id
                        result["skill_regression_gate"] = group.gate_result.model_dump(by_alias=True)
                        result["gate"]["checks"].append({
                            "name": "skill_regression_gate",
                            "passed": group.gate_result.passed,
                            "detail": group.gate_result.blocks,
                        })
                        result["gate"]["passed"] = (
                            result["gate"]["passed"] and group.gate_result.passed
                        )

            return result

        except Exception as e:
            logger.error(f"[Evolution] Comparison failed: {e}")
            return {"error": str(e)}

    async def list_by_proposal(self, proposal_id: str) -> List[VerificationRun]:
        """列出提案的所有验证记录"""
        db = get_mongo_db()
        cursor = db[self.COLLECTION].find({"proposal_id": proposal_id}).sort("created_at", -1)
        results = []
        async for doc in cursor:
            results.append(VerificationRun(**doc))
        return results

    async def get(self, verification_id: str) -> Optional[VerificationRun]:
        """获取验证记录"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one({"verification_id": verification_id})
        if not doc:
            return None
        return VerificationRun(**doc)

    async def _log_event(self, event_type: str, proposal_id: str, detail: Dict[str, Any]):
        """记录事件"""
        db = get_mongo_db()
        await db["evolution_event_log"].insert_one({
            "event_type": event_type,
            "proposal_id": proposal_id,
            "actor": "system",
            "detail": detail,
            "created_at": now_tz(),
        })


# 模块级单例
verification_service = VerificationService()
