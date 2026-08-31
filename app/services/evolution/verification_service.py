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
        from app.services.eval.runner_service import runner_service
        from app.services.eval.metrics_service import metrics_service

        # 加载提案
        proposal = await proposal_service.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        # 更新状态为 verifying
        await proposal_service.update_status(proposal_id, ProposalStatus.VERIFYING)

        verification_id = f"vrf_{uuid.uuid4().hex[:12]}"
        sandbox_path = ""

        try:
            # 获取当前 artifact 版本作为基线
            current_version = await artifact_registry.get_current_version(proposal.target_artifact_id)

            # 创建 sandbox
            sandbox_path = self._create_sandbox(proposal, current_version)

            # 确定 dataset_id（从 trigger run 获取）
            db = get_mongo_db()
            trigger_run = await db["eval_runs"].find_one({"run_id": proposal.trigger_run_id})
            dataset_id = trigger_run.get("dataset_id", "") if trigger_run else ""
            dataset_version = trigger_run.get("dataset_version") if trigger_run else None

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

            # 计算对比结果
            comparison = await self._compute_comparison(
                proposal.trigger_run_id, candidate_run_id, metrics_service
            )

            # 保存验证记录
            verification = VerificationRun(
                verification_id=verification_id,
                proposal_id=proposal_id,
                baseline_run_id=proposal.trigger_run_id,
                candidate_run_id=candidate_run_id,
                sandbox_path=sandbox_path,
                comparison_result=comparison,
                status="completed",
                completed_at=now_tz(),
            )
            await db[self.COLLECTION].insert_one(verification.model_dump(by_alias=True, exclude={"id"}))

            # 更新提案状态
            await proposal_service.update_status(proposal_id, ProposalStatus.VERIFIED)

            # 清理事件日志
            await self._log_event("verification_completed", proposal_id, {
                "verification_id": verification_id,
                "baseline_run": proposal.trigger_run_id,
                "candidate_run": candidate_run_id,
            })

            return verification

        except Exception as e:
            logger.error(f"[Evolution] Verification failed for {proposal_id}: {e}")
            await proposal_service.update_status(proposal_id, ProposalStatus.DRAFT)

            # 保存失败的验证记录
            db = get_mongo_db()
            failed_verification = VerificationRun(
                verification_id=verification_id,
                proposal_id=proposal_id,
                status="failed",
                sandbox_path=sandbox_path,
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
                    logger.info(f"[Evolution] Cleaned up sandbox: {sandbox_path}")
                except Exception as cleanup_err:
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
        self, baseline_run_id: str, candidate_run_id: str, metrics_service
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
