"""
Agent 自进化闭环模型与服务测试

验证自进化数据模型的序列化、枚举值和基本业务逻辑。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestEvolutionModels:
    """测试自进化数据模型"""

    def test_artifact_type_enum(self):
        """测试 ArtifactType 枚举"""
        from app.models.evolution import ArtifactType

        assert ArtifactType.SKILL.value == "skill"
        assert ArtifactType.PROMPT.value == "prompt"
        assert ArtifactType.POLICY.value == "policy"
        assert ArtifactType.RUBRIC.value == "rubric"
        assert ArtifactType.CASE.value == "case"

    def test_proposal_status_enum(self):
        """测试 ProposalStatus 枚举"""
        from app.models.evolution import ProposalStatus

        expected = ["draft", "pending_verify", "verifying", "verified",
                     "approved", "rejected", "promoted", "rollback", "stopped"]
        for val in expected:
            assert ProposalStatus(val).value == val

    def test_approval_action_enum(self):
        """测试 ApprovalAction 枚举"""
        from app.models.evolution import ApprovalAction

        assert ApprovalAction.APPROVE.value == "approve"
        assert ApprovalAction.REJECT.value == "reject"
        assert ApprovalAction.COMMENT.value == "comment"

    def test_stop_reason_enum(self):
        """测试 StopReason 枚举"""
        from app.models.evolution import StopReason

        assert StopReason.BUDGET_EXCEEDED.value == "budget_exceeded"
        assert StopReason.MANUAL.value == "manual"

    def test_trigger_type_enum(self):
        """测试 TriggerType 枚举"""
        from app.models.evolution import TriggerType

        assert TriggerType.RUN_COMPLETED.value == "run_completed"
        assert TriggerType.REGRESSION.value == "regression"
        assert TriggerType.BAD_CASE_THRESHOLD.value == "bad_case_threshold"
        assert TriggerType.SCHEDULED.value == "scheduled"

    def test_risk_level_enum(self):
        """测试 RiskLevel 枚举"""
        from app.models.evolution import RiskLevel

        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_artifact_version_model(self):
        """测试 ArtifactVersion 模型"""
        from app.models.evolution import ArtifactVersion, ArtifactType, ArtifactVersionStatus

        version = ArtifactVersion(
            artifact_id="art_skill_test",
            artifact_type=ArtifactType.SKILL,
            name="Test Skill",
            path="/skills/test/SKILL.md",
            version="1.0.0",
            content_hash="abc123",
            content_snapshot={"content": "# Test"},
            owner="system",
            status=ArtifactVersionStatus.ACTIVE,
        )

        assert version.artifact_id == "art_skill_test"
        assert version.version == "1.0.0"
        assert version.status == ArtifactVersionStatus.ACTIVE

        # 测试序列化
        dumped = version.model_dump(by_alias=True, exclude={"id"})
        assert dumped["artifact_id"] == "art_skill_test"
        assert dumped["content_snapshot"] == {"content": "# Test"}

    def test_artifact_registry_entry_model(self):
        """测试 ArtifactRegistryEntry 模型"""
        from app.models.evolution import ArtifactRegistryEntry, ArtifactType

        entry = ArtifactRegistryEntry(
            artifact_id="art_prompt_system",
            artifact_type=ArtifactType.PROMPT,
            name="System Prompt",
            current_version="2.1.0",
            owner="admin",
        )

        assert entry.artifact_id == "art_prompt_system"
        assert entry.current_version == "2.1.0"

    def test_proposal_model(self):
        """测试 Proposal 模型"""
        from app.models.evolution import (
            Proposal, ProposalStatus, ArtifactType,
            TriggerType, RiskLevel,
        )

        proposal = Proposal(
            proposal_id="prop_abc123",
            trigger_run_id="run_001",
            trigger_type=TriggerType.REGRESSION,
            target_artifact_id="art_skill_tushare",
            target_artifact_type=ArtifactType.SKILL,
            diff={"change_description": "Fix tool selection"},
            reason="Trend regression detected",
            sample_failure_ids=["trial_001", "trial_002"],
            risk_level=RiskLevel.MEDIUM,
            status=ProposalStatus.PENDING_VERIFY,
        )

        assert proposal.proposal_id == "prop_abc123"
        assert proposal.trigger_type == TriggerType.REGRESSION
        assert proposal.status == ProposalStatus.PENDING_VERIFY
        assert len(proposal.sample_failure_ids) == 2

        # 序列化测试
        dumped = proposal.model_dump(by_alias=True, exclude={"id"})
        assert dumped["proposal_id"] == "prop_abc123"
        assert dumped["trigger_type"] == "regression"

    def test_verification_run_model(self):
        """测试 VerificationRun 模型"""
        from app.models.evolution import VerificationRun

        vrf = VerificationRun(
            verification_id="vrf_xyz789",
            proposal_id="prop_abc123",
            baseline_run_id="run_001",
            candidate_run_id="run_002",
            sandbox_path="/tmp/evo_test",
            comparison_result={"pass_at_k": {"baseline": 0.8, "candidate": 0.9}},
            status="completed",
        )

        assert vrf.verification_id == "vrf_xyz789"
        assert vrf.comparison_result["pass_at_k"]["candidate"] == 0.9

    def test_approval_record_model(self):
        """测试 ApprovalRecord 模型"""
        from app.models.evolution import ApprovalRecord, ApprovalAction

        record = ApprovalRecord(
            reviewer="admin_user",
            action=ApprovalAction.APPROVE,
            comment="Looks good",
        )

        assert record.reviewer == "admin_user"
        assert record.action == ApprovalAction.APPROVE

    def test_evolution_receipt_model(self):
        """测试 EvolutionReceipt 模型"""
        from app.models.evolution import (
            EvolutionReceipt, ApprovalRecord, ApprovalAction, StopReason,
        )

        receipt = EvolutionReceipt(
            receipt_id="rcpt_001",
            proposal_id="prop_abc123",
            verification_id="vrf_xyz789",
            approval_records=[
                ApprovalRecord(reviewer="admin", action=ApprovalAction.APPROVE, comment="OK"),
            ],
            final_action="promoted",
            promoted_version="1.2.0",
        )

        assert receipt.receipt_id == "rcpt_001"
        assert receipt.final_action == "promoted"
        assert receipt.promoted_version == "1.2.0"
        assert len(receipt.approval_records) == 1

    def test_evolution_event_log_model(self):
        """测试 EvolutionEventLog 模型"""
        from app.models.evolution import EvolutionEventLog

        event = EvolutionEventLog(
            event_type="proposal_created",
            proposal_id="prop_abc123",
            artifact_id="art_skill_test",
            actor="system",
            detail={"trigger_type": "regression"},
        )

        assert event.event_type == "proposal_created"
        assert event.detail["trigger_type"] == "regression"


class TestEvolutionConfig:
    """测试自进化配置"""

    def test_evolution_config_defaults(self):
        """验证默认配置是生产安全的"""
        from app.core.config import settings

        assert settings.EVOLUTION_ENABLED is False
        assert settings.EVOLUTION_AUTOMATION_MODE == "manual"
        assert settings.EVOLUTION_HUMAN_GATE is True
        assert settings.EVOLUTION_TRIGGER_REGRESSION_THRESHOLD == 0.05
        assert settings.EVOLUTION_TRIGGER_BAD_CASE_COUNT == 10
        assert settings.EVOLUTION_BUDGET_MAX_RUNS_PER_DAY == 5


class TestClusteringUtils:
    """测试失败聚类工具函数"""

    def test_identify_primary_failure_surface_scorer_mapping(self):
        """测试评分器到失败面的映射"""
        from app.services.evolution.clustering import identify_primary_failure_surface

        # evidence_quality -> policy
        result = identify_primary_failure_surface({
            "by_scorer": [{"scorer": "evidence_quality", "count": 10}],
            "by_error": [],
        })
        assert result == "policy"

        # llm_judge -> rubric
        result = identify_primary_failure_surface({
            "by_scorer": [{"scorer": "llm_judge", "count": 5}],
            "by_error": [],
        })
        assert result == "rubric"

        # trajectory -> skill
        result = identify_primary_failure_surface({
            "by_scorer": [{"scorer": "trajectory", "count": 3}],
            "by_error": [],
        })
        assert result == "skill"

    def test_identify_primary_failure_surface_error_pattern(self):
        """测试错误模式到失败面的映射"""
        from app.services.evolution.clustering import identify_primary_failure_surface

        result = identify_primary_failure_surface({
            "by_scorer": [],
            "by_error": [{"pattern": "tool execution failed", "count": 5}],
        })
        assert result == "skill"

        result = identify_primary_failure_surface({
            "by_scorer": [],
            "by_error": [{"pattern": "format parse error", "count": 3}],
        })
        assert result == "prompt"

    def test_identify_primary_failure_surface_unknown(self):
        """测试无匹配时返回 unknown"""
        from app.services.evolution.clustering import identify_primary_failure_surface

        result = identify_primary_failure_surface({
            "by_scorer": [],
            "by_error": [],
        })
        assert result == "unknown"


class TestArtifactRegistryHelpers:
    """测试 artifact registry 辅助函数"""

    def test_bump_patch_version(self):
        """测试版本号递增"""
        from app.services.evolution.artifact_registry import _bump_patch_version

        assert _bump_patch_version("1.0.0") == "1.0.1"
        assert _bump_patch_version("2.3.9") == "2.3.10"
        assert _bump_patch_version("invalid") == "invalid"

    def test_parse_semver(self):
        """测试语义化版本解析"""
        from app.services.evolution.artifact_registry import _parse_semver

        assert _parse_semver("1.2.3") == (1, 2, 3)
        assert _parse_semver("invalid") is None
        assert _parse_semver("1.2") is None

    def test_compute_content_hash(self):
        """测试内容哈希计算"""
        from app.services.evolution.artifact_registry import _compute_content_hash

        hash1 = _compute_content_hash({"key": "value"})
        hash2 = _compute_content_hash({"key": "value"})
        hash3 = _compute_content_hash({"key": "different"})

        assert hash1 == hash2  # 相同内容 → 相同哈希
        assert hash1 != hash3  # 不同内容 → 不同哈希
        assert len(hash1) == 64  # SHA256 hex length


class TestProposalForbiddenCheck:
    """测试 forbidden target 拦截"""

    def test_forbidden_hardcoded_patterns(self):
        """测试硬编码禁止模式"""
        from app.services.evolution.proposal_service import ProposalService

        svc = ProposalService()
        assert svc._check_forbidden("core_code_main") is True
        assert svc._check_forbidden("test_split_validation") is True
        assert svc._check_forbidden("scorer_definition_base") is True
        assert svc._check_forbidden("art_skill_normal") is False

    def test_surface_to_artifact_type_mapping(self):
        """测试失败面到 artifact 类型的映射"""
        from app.services.evolution.proposal_service import ProposalService
        from app.models.evolution import ArtifactType

        svc = ProposalService()
        assert svc._surface_to_artifact_type("skill") == ArtifactType.SKILL
        assert svc._surface_to_artifact_type("prompt") == ArtifactType.PROMPT
        assert svc._surface_to_artifact_type("policy") == ArtifactType.POLICY
        assert svc._surface_to_artifact_type("rubric") == ArtifactType.RUBRIC
        assert svc._surface_to_artifact_type("case") == ArtifactType.CASE
        assert svc._surface_to_artifact_type("unknown") == ArtifactType.SKILL  # default
