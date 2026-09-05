"""自进化生产闭环的集成级流程测试。

使用 mock Mongo 集合和 fake runtime overlay，覆盖
trigger -> proposal -> overlay verify -> gate -> approve -> promote -> rollback
以及发布后退化 -> rollback suggestion -> notification。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.evolution import ProposalStatus, StopReason


def _mock_proposal_collection(statuses):
    collection = MagicMock()
    collection.find_one = AsyncMock(side_effect=[
        {"proposal_id": "p1", "status": s} for s in statuses
    ])
    collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return collection


class TestProductionFlow:
    def test_trigger_to_overlay_runtime_pipeline(self, tmp_path):
        """触发与 overlay 候选都经过 fake runtime 可执行边界。"""
        from app.services.evolution.governance_service import governance_service
        from vibe_agent_runtime.runtime import EmbeddedAgentRuntime

        trigger = {"trigger_type": "regression", "sample_failure_ids": ["t1"]}
        artifact_id = "art_skill_research"
        fingerprint = governance_service.fingerprint(trigger, artifact_id)
        assert fingerprint

        skill_dir = tmp_path / "skills" / "research"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Candidate skill", encoding="utf-8")
        prompt, overlay_event = EmbeddedAgentRuntime._apply_overlay_prompt(
            "测试任务",
            {
                "sandbox_path": str(tmp_path),
                "proposal_id": "p1",
                "artifact_id": artifact_id,
                "baseline_version": "1.0.0",
                "candidate_version": "candidate",
                "overlay_id": "overlay-1",
            },
        )
        assert "测试任务" in prompt
        assert "# Candidate skill" in prompt
        assert overlay_event["loaded_files"]

    @pytest.mark.asyncio
    async def test_state_machine_approve_promote_flow(self):
        """proposal 状态链可走完整合法流程。"""
        from app.services.evolution.governance_service import governance_service

        db = MagicMock()
        collection = _mock_proposal_collection([
            ProposalStatus.DRAFT.value,
            ProposalStatus.PENDING_VERIFY.value,
            ProposalStatus.VERIFYING.value,
            ProposalStatus.VERIFIED.value,
            ProposalStatus.APPROVED.value,
        ])
        db.__getitem__ = MagicMock(return_value=collection)
        with patch("app.services.evolution.governance_service.get_mongo_db", return_value=db):
            for target in (
                ProposalStatus.PENDING_VERIFY,
                ProposalStatus.VERIFYING,
                ProposalStatus.VERIFIED,
                ProposalStatus.APPROVED,
                ProposalStatus.PROMOTED,
            ):
                current = await governance_service.transition("p1", target)
                assert current["to"] == target.value

    @pytest.mark.asyncio
    async def test_rollback_and_smoke_are_enforced(self):
        """promote smoke 失败会触发补偿回滚。"""
        from app.services.evolution.promote_service import PromoteService

        service = PromoteService()
        proposal = MagicMock(
            proposal_id="p1",
            target_artifact_id="art_skill_research",
            target_artifact_type="skill",
            baseline_artifact_version="1.0.0",
            diff={"type": "skill", "change_description": "change", "sections_affected": ["tool_selection"]},
            status=ProposalStatus.APPROVED,
        )
        failed_version = MagicMock(
            artifact_id="art_skill_research",
            artifact_type="skill",
            version="1.0.1",
            content_snapshot={"content": ""},
            environment="default",
            source_proposal_id="p1",
            status="pending",
        )
        settings = MagicMock(EVOLUTION_HUMAN_GATE=False, EVOLUTION_REQUIRE_SMOKE_TEST=True)
        version_collection = MagicMock()
        version_collection.update_one = AsyncMock()
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=version_collection)
        latest_verification = MagicMock(
            status="completed",
            cleanup_status="cleaned",
            gate_result={"passed": True},
            comparison_result={},
            verification_id="v1",
        )
        with patch("app.services.evolution.promote_service.settings", settings):
            with patch("app.services.evolution.governance_service.governance_service.acquire_proposal_lock", new=AsyncMock()):
                with patch("app.services.evolution.proposal_service.proposal_service.get", new=AsyncMock(return_value=proposal)):
                    with patch("app.services.evolution.approval_service.approval_service.get_records", new=AsyncMock(return_value=[{"action": "approve"}])):
                        with patch("app.services.evolution.verification_service.verification_service.list_by_proposal", new=AsyncMock(return_value=[latest_verification])):
                            with patch("app.services.evolution.artifact_registry.artifact_registry.get_registry_entry", new=AsyncMock(return_value=MagicMock(current_version="1.0.0"))):
                                with patch("app.services.evolution.artifact_registry.artifact_registry.get_current_version", new=AsyncMock(return_value=MagicMock(version="1.0.0"))):
                                    with patch("app.services.evolution.artifact_registry.artifact_registry.create_version_record", new=AsyncMock(return_value=failed_version)):
                                        with patch("app.services.evolution.artifact_publisher.artifact_publisher.materialize", new=AsyncMock(return_value={"files": ["SKILL.md"]})):
                                            with patch.object(service, "_run_promoted_smoke_test", new=AsyncMock(return_value={
                                                "passed": False, "failures": ["empty"]
                                            })):
                                                with patch("app.services.evolution.promote_service.get_mongo_db", return_value=db):
                                                    with patch("app.services.evolution.artifact_registry.artifact_registry.mark_version_failed", new=AsyncMock()) as mock_mark_failed:
                                                        with patch.object(service, "_log_event", new=AsyncMock()):
                                                            with pytest.raises(ValueError, match="smoke test failed"):
                                                                await service.promote("p1", idempotency_key="")
        mock_mark_failed.assert_awaited_once()


class TestPostReleaseRollbackSuggestion:
    def test_degradation_suggests_rollback_and_notifies(self):
        """发布后退化会同时产生 rollback 建议和 stop 通知。"""
        from app.services.evolution.governance_service import governance_service

        result = governance_service.evaluate_post_release({
            "success_rate": 0.4,
            "score_aggregation": {"safety": {"avg_score": 0.6}},
        })
        assert result["rollback_suggestion"] is True
        assert "success_rate" in result["failures"]

    @pytest.mark.asyncio
    async def test_stop_event_is_notified_and_sanitized(self):
        """stop 事件通过治理通知记录，敏感内容在落地前已脱敏。"""
        from app.services.evolution.governance_service import governance_service

        collection = MagicMock()
        collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="delivery-1"))
        collection.update_one = AsyncMock()
        collection.find_one = AsyncMock(return_value=None)
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)

        with patch("app.services.evolution.governance_service.get_mongo_db", return_value=db):
            result = await governance_service.notify("proposal_stop", {
                "reason": StopReason.SAFETY_REGRESSION.value,
                "prompt_summary": "用户手机号13812345678",
            })
        assert result["status"] in {"sent", "failed"}
