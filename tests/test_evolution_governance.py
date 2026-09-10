"""生产自进化治理策略和 candidate overlay 测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEvolutionGovernance:
    def test_fingerprint_is_stable(self):
        from app.services.evolution.governance_service import governance_service

        trigger = {"trigger_type": "run_completed", "sample_failure_ids": ["t1"]}
        assert governance_service.fingerprint(trigger, "art_skill_x") == governance_service.fingerprint(trigger, "art_skill_x")
        assert governance_service.fingerprint(trigger, "art_skill_x") != governance_service.fingerprint(trigger, "art_skill_y")

    def test_change_budget_rejects_large_diff(self):
        from app.services.evolution.governance_service import governance_service

        settings = MagicMock(EVOLUTION_CHANGE_BUDGET_CHARS=10)
        with patch("app.services.evolution.governance_service.get_settings", return_value=settings):
            with pytest.raises(ValueError, match="budget exceeded"):
                governance_service.validate_change_budget({"change_description": "x" * 100})

    @pytest.mark.asyncio
    async def test_transition_uses_compare_and_set(self):
        from app.services.evolution.governance_service import governance_service
        from app.models.evolution import ProposalStatus

        db = MagicMock()
        collection = MagicMock()
        collection.find_one = AsyncMock(return_value={"proposal_id": "p1", "status": "pending_verify"})
        collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        db.__getitem__ = MagicMock(return_value=collection)

        with patch("app.services.evolution.governance_service.get_mongo_db", return_value=db):
            result = await governance_service.transition("p1", ProposalStatus.VERIFYING)

        assert result == {"from": "pending_verify", "to": "verifying"}
        assert collection.update_one.await_args.args[0] == {"proposal_id": "p1", "status": "pending_verify"}

    @pytest.mark.asyncio
    async def test_transition_rejects_skip(self):
        from app.services.evolution.governance_service import governance_service
        from app.models.evolution import ProposalStatus

        db = MagicMock()
        collection = MagicMock()
        collection.find_one = AsyncMock(return_value={"proposal_id": "p1", "status": "pending_verify"})
        db.__getitem__ = MagicMock(return_value=collection)

        with patch("app.services.evolution.governance_service.get_mongo_db", return_value=db):
            with pytest.raises(ValueError, match="invalid proposal transition"):
                await governance_service.transition("p1", ProposalStatus.APPROVED)


class TestCandidateOverlay:
    def test_overlay_prompt_contains_candidate_file_and_metadata(self, tmp_path):
        from vibe_agent_runtime.runtime import EmbeddedAgentRuntime

        candidate = tmp_path / "skills" / "research" / "SKILL.md"
        candidate.parent.mkdir(parents=True)
        candidate.write_text("# Candidate research skill", encoding="utf-8")

        prompt, event = EmbeddedAgentRuntime._apply_overlay_prompt(
            "原始任务",
            {
                "sandbox_path": str(tmp_path),
                "overlay_id": "overlay_1",
                "proposal_id": "proposal_1",
                "artifact_id": "art_skill_research",
                "baseline_version": "1.0.0",
                "candidate_version": "candidate",
            },
        )

        assert "原始任务" in prompt
        assert "Candidate research skill" in prompt
        assert event["overlay_id"] == "overlay_1"
        assert "skills/research/SKILL.md" in event["loaded_files"]

    def test_overlay_missing_directory_fails_closed(self, tmp_path):
        from vibe_agent_runtime.runtime import EmbeddedAgentRuntime

        with pytest.raises(RuntimeError, match="does not exist"):
            EmbeddedAgentRuntime._apply_overlay_prompt(
                "task", {"sandbox_path": str(tmp_path / "missing")}
            )


class TestPromoteSmokeTest:
    def test_smoke_test_rejects_empty_candidate(self):
        from app.services.evolution.promote_service import PromoteService

        proposal = MagicMock(diff={})
        result = PromoteService._run_smoke_test(proposal)
        assert result["passed"] is False
        assert result["failures"]

    def test_smoke_test_accepts_structured_candidate(self):
        from app.services.evolution.promote_service import PromoteService

        proposal = MagicMock(diff={
            "type": "skill",
            "change_description": "improve tool routing",
            "sections_affected": ["tool_selection"],
        })
        result = PromoteService._run_smoke_test(proposal)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_promoted_smoke_test_requires_active_snapshot(self):
        from app.models.evolution import ArtifactType
        from app.services.evolution.promote_service import PromoteService

        service = PromoteService()
        empty_version = MagicMock(artifact_type=ArtifactType.PROMPT, content_snapshot={})
        good_version = MagicMock(artifact_type=ArtifactType.PROMPT, content_snapshot={"content": "candidate"})
        assert (await service._run_promoted_smoke_test(empty_version))["passed"] is False
        assert (await service._run_promoted_smoke_test(good_version))["passed"] is True


class TestEvolutionNotifications:
    @pytest.mark.asyncio
    async def test_delivery_failure_is_recorded(self):
        from app.services.evolution.governance_service import governance_service

        collection = MagicMock()
        collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="delivery-1"))
        collection.update_one = AsyncMock()
        collection.find_one = AsyncMock(return_value=None)
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)

        with patch("app.services.evolution.governance_service.get_mongo_db", return_value=db):
            result = await governance_service.notify("verification_failed", {"error": "test"})

        assert result["status"] == "failed"
        collection.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_failed_notifications(self):
        from app.services.evolution.governance_service import governance_service

        collection = MagicMock()
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[{
            "_id": "delivery-1", "event": "verification_failed", "detail": {}, "attempts": 1,
        }])
        collection.find = MagicMock(return_value=cursor)
        collection.update_one = AsyncMock()
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)
        with patch("app.services.evolution.governance_service.get_mongo_db", return_value=db):
            with patch.object(
                governance_service,
                "_deliver_notification",
                new=AsyncMock(return_value=("sent", None)),
            ):
                result = await governance_service.retry_failed_notifications()
        assert result["retried"] == 1
        collection.update_one.assert_awaited_once()


class TestRepeatedFailureStopHook:
    @pytest.mark.asyncio
    async def test_repeated_failure_stops_proposal(self):
        from app.models.evolution import StopReason
        from app.services.evolution.governance_service import governance_service

        collection = MagicMock()
        collection.count_documents = AsyncMock(return_value=3)
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)
        with patch("app.services.evolution.governance_service.get_mongo_db", return_value=db):
            with patch.object(governance_service, "stop", new=AsyncMock()) as mock_stop:
                with pytest.raises(ValueError, match="repeated failure"):
                    await governance_service.assert_no_repeated_failure(
                        "fingerprint-1", "art_skill_x", "proposal-1"
                    )
        assert mock_stop.await_args.args[1] == StopReason.REPEATED_FAILURES


class TestPostReleaseObservation:
    def test_degradation_returns_rollback_suggestion(self):
        from app.services.evolution.governance_service import governance_service
        result = governance_service.evaluate_post_release({
            "success_rate": 0.5,
            "score_aggregation": {"safety": {"avg_score": 0.9}},
        })
        assert result["passed"] is False
        assert result["rollback_suggestion"] is True
        assert "success_rate" in result["failures"]

    def test_healthy_metrics_pass(self):
        from app.services.evolution.governance_service import governance_service
        result = governance_service.evaluate_post_release({
            "success_rate": 0.95,
            "score_aggregation": {
                "safety": {"avg_score": 0.95},
                "evidence_quality": {"avg_score": 0.85},
            },
            "latency": {"mean_ms": 1000},
            "cost": {"total_usd": 0.1},
        })
        assert result["passed"] is True


class TestScheduledTrigger:
    @pytest.mark.asyncio
    async def test_scheduled_check_fires_after_lock(self):
        from app.services.evolution.trigger_service import TriggerService
        from app.services.evolution.governance_service import governance_service

        svc = TriggerService()
        settings = MagicMock(EVOLUTION_SCHEDULE_CRON="* * * * *")
        eval_runs = MagicMock()
        eval_runs.find_one = AsyncMock(return_value={"run_id": "run-1", "dataset_id": "ds-1"})
        db = MagicMock()
        db.__getitem__ = MagicMock(side_effect=lambda name: eval_runs if name == "eval_runs" else MagicMock())

        trigger = {"trigger_type": "scheduled", "trigger_run_id": "run-1", "dataset_id": "ds-1"}
        with patch("app.services.evolution.trigger_service.settings", settings):
            with patch.object(governance_service, "acquire_window_lock", new=AsyncMock(return_value=True)):
                with patch.object(svc, "_evaluate_triggers", new=AsyncMock(return_value=trigger)):
                    with patch.object(svc, "_log_event", new=AsyncMock()):
                        with patch("app.services.evolution.trigger_service.get_mongo_db", return_value=db):
                            result = await svc.scheduled_check()
        assert result["trigger_type"] == "scheduled"

    @pytest.mark.asyncio
    async def test_scheduled_check_skips_when_lock_held(self):
        from app.services.evolution.trigger_service import TriggerService
        from app.services.evolution.governance_service import governance_service

        svc = TriggerService()
        settings = MagicMock(EVOLUTION_SCHEDULE_CRON="* * * * *")
        with patch("app.services.evolution.trigger_service.settings", settings):
            with patch.object(governance_service, "acquire_window_lock", new=AsyncMock(return_value=False)):
                assert await svc.scheduled_check() is None


class TestReceiptIdempotency:
    @pytest.mark.asyncio
    async def test_create_returns_existing_receipt(self):
        from app.models.evolution import EvolutionReceipt
        from app.services.evolution.receipt_service import ReceiptService

        existing = {"receipt_id": "rcpt_1", "idempotency_key": "key-1", "proposal_id": "p1"}
        collection = MagicMock()
        collection.find_one = AsyncMock(return_value=existing)
        collection.insert_one = AsyncMock()
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)
        with patch("app.services.evolution.receipt_service.get_mongo_db", return_value=db):
            receipt = await ReceiptService().create(EvolutionReceipt(
                receipt_id="rcpt_new", proposal_id="p1", idempotency_key="key-1"
            ))
        assert receipt.receipt_id == "rcpt_1"
        collection.insert_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_promote_returns_existing_receipt(self):
        from app.models.evolution import EvolutionReceipt
        from app.services.evolution.promote_service import PromoteService

        existing = EvolutionReceipt(
            receipt_id="rcpt_old", proposal_id="p1", idempotency_key="key-1"
        )
        with patch(
            "app.services.evolution.receipt_service.receipt_service.get_by_idempotency_key",
            new=AsyncMock(return_value=existing),
        ):
            receipt = await PromoteService().promote("p1", idempotency_key="key-1")
        assert receipt.receipt_id == "rcpt_old"


class TestSkillWriteBack:
    @pytest.mark.asyncio
    async def test_writes_skill_to_temp_and_invalidates_cache(self, tmp_path):
        from app.models.evolution import ArtifactType
        from app.services.evolution.promote_service import PromoteService

        version = MagicMock(
            artifact_id="art_skill_research",
            artifact_type=ArtifactType.SKILL,
            content_snapshot={"content": "# Research"},
        )
        redis = AsyncMock()
        redis.delete = AsyncMock()
        with patch("app.core.database.get_redis_client", return_value=redis):
            await PromoteService()._write_skill_version_to_disk(version, skills_dir=tmp_path)
        skill_file = tmp_path / "research" / "SKILL.md"
        assert skill_file.read_text(encoding="utf-8") == "# Research"
        redis.delete.assert_awaited()


class TestCandidateDataScope:
    def test_validation_scope_is_allowed(self):
        from app.services.eval.runner_service import EvalRunnerService

        EvalRunnerService._validate_evolution_scope(
            {"evolution_proposal_id": "p1", "split": "validation", "overlay_dataset_version": "1.0.0"},
            [{"case_id": "c1", "split": "validation"}],
            "1.0.0",
        )

    def test_test_split_is_rejected(self):
        from app.services.eval.runner_service import EvalRunnerService

        with pytest.raises(ValueError, match="split is not allowed"):
            EvalRunnerService._validate_evolution_scope(
                {"evolution_proposal_id": "p1", "split": "test"}, [], "1.0.0"
            )

    def test_overlay_version_mismatch_is_rejected(self):
        from app.services.eval.runner_service import EvalRunnerService

        with pytest.raises(ValueError, match="dataset version"):
            EvalRunnerService._validate_evolution_scope(
                {"evolution_proposal_id": "p1", "overlay_dataset_version": "1.0.0"},
                [],
                "2.0.0",
            )


class TestRollbackIntegrity:
    @pytest.mark.asyncio
    async def test_active_version_rollback_is_idempotent(self):
        from app.models.evolution import ArtifactVersionStatus
        from app.services.evolution.artifact_registry import ArtifactRegistryService, _compute_content_hash

        snapshot = {"content": "stable"}
        target = {
            "artifact_id": "art_skill_demo",
            "artifact_type": "skill",
            "name": "demo",
            "path": "demo/SKILL.md",
            "version": "1.0.0",
            "content_hash": _compute_content_hash(snapshot),
            "content_snapshot": snapshot,
            "status": ArtifactVersionStatus.ACTIVE.value,
        }
        collection = MagicMock()
        collection.find_one = AsyncMock(return_value=target)
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)
        service = ArtifactRegistryService()
        with patch("app.services.evolution.artifact_registry.get_mongo_db", return_value=db):
            result = await service.rollback("art_skill_demo", "1.0.0")
        assert result.version == "1.0.0"
        assert result.status == ArtifactVersionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_hash_mismatch_rejects_rollback(self):
        from app.services.evolution.artifact_registry import ArtifactRegistryService

        target = {
            "artifact_id": "art_skill_demo",
            "artifact_type": "skill",
            "name": "demo",
            "path": "demo/SKILL.md",
            "version": "1.0.0",
            "content_hash": "wrong-hash",
            "content_snapshot": {"content": "stable"},
            "status": "superseded",
        }
        collection = MagicMock()
        collection.find_one = AsyncMock(return_value=target)
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)
        service = ArtifactRegistryService()
        with patch("app.services.evolution.artifact_registry.get_mongo_db", return_value=db):
            with pytest.raises(ValueError, match="hash mismatch"):
                await service.rollback("art_skill_demo", "1.0.0")
