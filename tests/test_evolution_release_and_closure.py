"""自进化发布硬化和生产闭环测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestArtifactPublisher:
    @pytest.mark.asyncio
    async def test_skill_materializes_to_configured_runtime_root(self, tmp_path):
        from app.models.evolution import ArtifactType, ArtifactVersion
        from app.services.evolution.artifact_publisher import artifact_publisher

        version = ArtifactVersion(
            artifact_id="art_skill_research",
            artifact_type=ArtifactType.SKILL,
            name="Research",
            version="1.0.1",
            content_snapshot={"content": "# Candidate Research"},
        )
        settings = MagicMock(EVOLUTION_ARTIFACT_RUNTIME_ROOT=str(tmp_path))
        with patch("app.services.evolution.artifact_publisher.settings", settings):
            result = await artifact_publisher.materialize(version)

        skill_file = tmp_path / "default" / "skills" / "user" / "research" / "SKILL.md"
        assert skill_file.read_text(encoding="utf-8") == "# Candidate Research"
        assert result["files"] == [str(skill_file)]

    @pytest.mark.asyncio
    async def test_non_skill_artifact_materializes_to_type_directory(self, tmp_path):
        from app.models.evolution import ArtifactType, ArtifactVersion
        from app.services.evolution.artifact_publisher import artifact_publisher

        for artifact_type in (
            ArtifactType.PROMPT,
            ArtifactType.POLICY,
            ArtifactType.RUBRIC,
            ArtifactType.CASE,
        ):
            artifact_id = f"art_{artifact_type.value}_demo"
            version = ArtifactVersion(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                name="Demo",
                version="1.0.1",
                content_snapshot={"content": "candidate"},
            )
            settings = MagicMock(EVOLUTION_ARTIFACT_RUNTIME_ROOT=str(tmp_path))
            with patch("app.services.evolution.artifact_publisher.settings", settings):
                result = await artifact_publisher.materialize(version)

            target = (
                tmp_path
                / "default"
                / "artifacts"
                / artifact_type.value
                / artifact_id
                / "1.0.1"
                / "artifact.json"
            )
            assert target.is_file()
            assert result["artifact_type"] == artifact_type.value


class TestSkillsRuntimeCompat:
    def test_skills_loader_reads_new_root_then_legacy_user_dir(self, tmp_path, monkeypatch):
        from vibe_agent_runtime.runtime import embedded_agent_runtime

        embedded_agent_runtime._bootstrap()
        from src.agent.skills import SkillsLoader, USER_SKILLS_DIR

        new_root = tmp_path / "new-root"
        new_skill = new_root / "skills" / "user" / "research"
        new_skill.mkdir(parents=True)
        (new_skill / "SKILL.md").write_text(
            "---\nname: research\n---\n# New research",
            encoding="utf-8",
        )

        legacy_root = tmp_path / "legacy-root"
        legacy_skill = legacy_root / "general"
        legacy_skill.mkdir(parents=True)
        (legacy_skill / "SKILL.md").write_text(
            "---\nname: general\n---\n# Legacy general",
            encoding="utf-8",
        )

        monkeypatch.setenv("EVOLUTION_SKILL_RUNTIME_ROOT", str(new_root))
        with patch("src.agent.skills.USER_SKILLS_DIR", legacy_root):
            loader = SkillsLoader()
        names = [skill.name for skill in loader.skills]
        assert "research" in names
        assert "general" in names
        assert loader.get_content("research").startswith("<skill name=\"research\">")


class TestPromoteHardBoundary:
    @pytest.mark.asyncio
    async def test_successful_promote_switches_pointer_and_records_receipt(self):
        from app.models.evolution import ArtifactType, ProposalStatus
        from app.services.evolution.promote_service import PromoteService

        service = PromoteService()
        proposal = MagicMock(
            proposal_id="p1",
            target_artifact_id="art_skill_research",
            target_artifact_type=ArtifactType.SKILL,
            baseline_artifact_version="1.0.0",
            diff={"type": "skill", "change_description": "change", "sections_affected": ["tool_selection"]},
            status=ProposalStatus.APPROVED,
        )
        version = MagicMock(
            artifact_id="art_skill_research",
            artifact_type=ArtifactType.SKILL,
            version="1.0.1",
            content_snapshot={"content": "# v2"},
            status="pending",
        )
        settings = MagicMock(EVOLUTION_HUMAN_GATE=False, EVOLUTION_REQUIRE_SMOKE_TEST=True)
        verification = MagicMock(
            status="completed",
            cleanup_status="cleaned",
            gate_result={"passed": True},
            comparison_result={},
            verification_id="v1",
        )
        version_collection = MagicMock()
        version_collection.update_one = AsyncMock()
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=version_collection)

        with patch("app.services.evolution.promote_service.settings", settings):
            with patch("app.services.evolution.governance_service.governance_service.acquire_proposal_lock", new=AsyncMock()):
                with patch("app.services.evolution.proposal_service.proposal_service.get", new=AsyncMock(return_value=proposal)):
                    with patch("app.services.evolution.approval_service.approval_service.get_records", new=AsyncMock(return_value=[{"reviewer": "admin", "action": "approve", "comment": "ok"}])):
                        with patch("app.services.evolution.verification_service.verification_service.list_by_proposal", new=AsyncMock(return_value=[verification])):
                            with patch("app.services.evolution.artifact_registry.artifact_registry.get_registry_entry", new=AsyncMock(return_value=MagicMock(current_version="1.0.0"))):
                                with patch("app.services.evolution.artifact_registry.artifact_registry.get_current_version", new=AsyncMock(return_value=MagicMock(version="1.0.0"))):
                                    with patch("app.services.evolution.artifact_registry.artifact_registry.create_version_record", new=AsyncMock(return_value=version)):
                                        with patch("app.services.evolution.artifact_publisher.artifact_publisher.materialize", new=AsyncMock(return_value={"files": ["SKILL.md"]})):
                                            with patch.object(service, "_run_promoted_smoke_test", new=AsyncMock(return_value={"passed": True, "failures": []})):
                                                with patch("app.services.evolution.artifact_registry.artifact_registry.activate_version", new=AsyncMock(return_value=version)) as activate:
                                                    with patch("app.services.evolution.proposal_service.proposal_service.update_status", new=AsyncMock()):
                                                        with patch("app.services.evolution.receipt_service.receipt_service.create", new=AsyncMock()) as receipt_create:
                                                            with patch("app.services.evolution.promote_service.get_mongo_db", return_value=db):
                                                                with patch.object(service, "_log_event", new=AsyncMock()):
                                                                    receipt = await service.promote("p1")

        activate.assert_awaited_once()
        receipt_create.assert_awaited_once()
        assert receipt.release_status == "succeeded"
        assert receipt.before_version == "1.0.0"
        assert receipt.after_version == "1.0.1"

    @pytest.mark.asyncio
    async def test_rollback_materialization_failure_keeps_current_version(self):
        from app.models.evolution import ArtifactType
        from app.services.evolution.promote_service import PromoteService

        service = PromoteService()
        target = MagicMock(
            artifact_id="art_skill_research",
            artifact_type=ArtifactType.SKILL,
            version="1.0.0",
            content_snapshot={"content": "# stable"},
            status="superseded",
        )
        with patch("app.services.evolution.receipt_service.receipt_service.get_by_idempotency_key", new=AsyncMock(return_value=None)):
            with patch("app.services.evolution.artifact_registry.artifact_registry.get_version", new=AsyncMock(return_value=target)):
                with patch("app.services.evolution.artifact_registry.artifact_registry.get_current_version", new=AsyncMock(return_value=MagicMock(version="1.0.0"))):
                    with patch("app.services.evolution.artifact_publisher.artifact_publisher.materialize", new=AsyncMock(side_effect=ValueError("disk full"))):
                        with patch("app.services.evolution.artifact_registry.artifact_registry.activate_version", new=AsyncMock()) as activate:
                            with patch.object(service, "_log_event", new=AsyncMock()):
                                with pytest.raises(ValueError, match="disk full"):
                                    await service.rollback("art_skill_research", "1.0.0")
        activate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_successful_rollback_switches_pointer_and_records_audit(self):
        from app.models.evolution import ArtifactType
        from app.services.evolution.promote_service import PromoteService

        service = PromoteService()
        target = MagicMock(
            artifact_id="art_skill_research",
            artifact_type=ArtifactType.SKILL,
            version="1.0.0",
            content_snapshot={"content": "# stable"},
            status="superseded",
        )
        before = MagicMock(version="1.0.1")
        version_collection = MagicMock()
        version_collection.update_one = AsyncMock()
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=version_collection)

        with patch("app.services.evolution.receipt_service.receipt_service.get_by_idempotency_key", new=AsyncMock(return_value=None)):
            with patch("app.services.evolution.artifact_registry.artifact_registry.get_version", new=AsyncMock(return_value=target)):
                with patch("app.services.evolution.artifact_registry.artifact_registry.get_current_version", new=AsyncMock(return_value=before)):
                    with patch("app.services.evolution.artifact_publisher.artifact_publisher.materialize", new=AsyncMock(return_value={"files": ["SKILL.md"]})):
                        with patch.object(service, "_run_promoted_smoke_test", new=AsyncMock(return_value={"passed": True, "failures": []})):
                            with patch("app.services.evolution.artifact_registry.artifact_registry.activate_version", new=AsyncMock(return_value=target)):
                                with patch("app.services.evolution.receipt_service.receipt_service.create", new=AsyncMock()) as receipt_create:
                                    with patch("app.services.evolution.promote_service.get_mongo_db", return_value=db):
                                        with patch.object(service, "_log_event", new=AsyncMock()):
                                            receipt = await service.rollback(
                                                "art_skill_research",
                                                "1.0.0",
                                            )

        receipt_create.assert_awaited_once()
        assert receipt.release_status == "succeeded"
        assert receipt.before_version == "1.0.1"
        assert receipt.after_version == "1.0.0"


class TestProductionClosure:
    def test_verification_uses_frozen_proposal_baseline(self):
        from app.services.evolution.verification_service import VerificationService

        proposal = MagicMock(baseline_artifact_version="1.0.0")
        current = MagicMock(version="1.2.0")
        assert VerificationService._frozen_baseline(proposal, current) == "1.0.0"

    @pytest.mark.asyncio
    async def test_baseline_drift_blocks_verification(self):
        from app.services.evolution.verification_service import verification_service

        proposal = MagicMock(
            proposal_id="p1",
            target_artifact_id="art_skill_general",
            baseline_artifact_version="1.0.0",
        )
        current = MagicMock(version="1.1.0")
        with patch("app.services.evolution.proposal_service.proposal_service.get", new=AsyncMock(return_value=proposal)):
            with patch("app.services.evolution.artifact_registry.artifact_registry.get_current_version", new=AsyncMock(return_value=current)):
                with pytest.raises(ValueError, match="baseline drift"):
                    await verification_service.run_verification("p1")

    @pytest.mark.asyncio
    async def test_cooldown_blocks_new_proposal(self):
        from app.services.evolution.governance_service import governance_service
        from app.services.evolution.proposal_service import proposal_service

        collection = MagicMock()
        collection.insert_one = AsyncMock()
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)
        trigger = {
            "trigger_type": "regression",
            "trigger_run_id": "run-1",
            "dataset_id": "ds-1",
            "target_surface": "skill",
            "sample_failure_ids": [],
        }
        with patch("app.services.evolution.governance_service.governance_service.find_active_duplicate", new=AsyncMock(return_value=None)):
            with patch("app.services.evolution.governance_service.governance_service.check_cooldown", new=AsyncMock(return_value={
                "blocked": True,
                "cooldown_minutes": 60,
                "latest_proposal_id": "prop_old",
            })):
                with patch.object(proposal_service, "_log_event", new=AsyncMock()):
                    with patch("app.services.evolution.proposal_service.get_mongo_db", return_value=db):
                        assert await proposal_service.create_from_trigger(trigger) is None
        collection.insert_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cooldown_expiry_allows_new_proposal(self):
        from app.services.evolution.governance_service import governance_service
        from app.services.evolution.proposal_service import proposal_service

        collection = MagicMock()
        collection.insert_one = AsyncMock()
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=collection)
        trigger = {
            "trigger_type": "regression",
            "trigger_run_id": "run-2",
            "dataset_id": "ds-1",
            "target_surface": "skill",
            "sample_failure_ids": ["t1"],
        }
        registry = MagicMock(current_version="1.0.0", path="skill")
        with patch("app.services.evolution.governance_service.governance_service.find_active_duplicate", new=AsyncMock(return_value=None)):
            with patch("app.services.evolution.governance_service.governance_service.check_cooldown", new=AsyncMock(return_value=None)):
                with patch("app.services.evolution.artifact_registry.artifact_registry.get_registry_entry", new=AsyncMock(return_value=registry)):
                    with patch("app.services.evolution.artifact_registry.artifact_registry.get_version", new=AsyncMock(return_value=MagicMock(content_snapshot={"content": "# stable"}))):
                        with patch("app.services.evolution.governance_service.governance_service.validate_target", new=AsyncMock()):
                            with patch.object(proposal_service, "_log_event", new=AsyncMock()):
                                with patch("app.services.evolution.proposal_service.get_mongo_db", return_value=db):
                                    proposal = await proposal_service.create_from_trigger(trigger)
        assert proposal is not None
        collection.insert_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_release_observe_creates_tracked_follow_up_actions(self):
        from app.services.evolution.governance_service import governance_service

        receipt = MagicMock(
            receipt_id="rcpt_1",
            artifact_id="art_skill_general",
            proposal_id="prop_1",
            baseline_artifact_version="1.0.0",
        )
        with patch.object(
            governance_service,
            "create_follow_up_action",
            new=AsyncMock(side_effect=[
                {"action_id": "evact_1", "escalation_level": 3, "action_type": "rollback"},
                {"action_id": "evact_2", "escalation_level": 4, "action_type": "stop"},
            ]),
        ):
            result = await governance_service.route_post_release_observation(receipt, {
                "success_rate": 0.2,
                "score_aggregation": {"safety": {"avg_score": 0.3}},
            })

        assert result["rollback_suggestion"] is True
        assert [action["action_type"] for action in result["follow_up_actions"]] == ["rollback", "stop"]
        assert result["event_chain"][-1]["event"] == "follow_up_action_created"


class TestOverlayIsolation:
    def test_overlay_rejects_symlink_escape(self, tmp_path):
        from vibe_agent_runtime.runtime import EmbeddedAgentRuntime

        outside = tmp_path / "outside.txt"
        outside.write_text("formal secret", encoding="utf-8")
        candidate = tmp_path / "candidate"
        candidate.mkdir()
        (candidate / "SKILL.md").symlink_to(outside)

        with pytest.raises(RuntimeError, match="symlink"):
            EmbeddedAgentRuntime._apply_overlay_prompt(
                "task",
                {"sandbox_path": str(candidate)},
            )

    def test_overlay_rejects_protected_runtime_root(self):
        from vibe_agent_runtime.runtime import EmbeddedAgentRuntime
        from pathlib import Path

        violations = EmbeddedAgentRuntime._validate_overlay_boundary(
            Path(__file__).resolve().parents[1]
        )
        assert violations
