"""Skill 执行评测与配对回归测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "vibe_agent_runtime" / "vendor"))


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self._docs = list(docs)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> Dict[str, Any]:
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return doc

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self


class FakeCollection:
    def __init__(self, docs: Optional[List[Dict[str, Any]]] = None) -> None:
        self.docs = list(docs or [])

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: Optional[Dict[str, Any]] = None) -> FakeCursor:
        query = query or {}
        return FakeCursor([
            dict(doc) for doc in self.docs
            if self._matches(doc, query)
        ])

    @staticmethod
    def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True

    async def insert_one(self, doc: Dict[str, Any]):
        self.docs.append(doc)
        return type("Result", (), {"inserted_id": None})()

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any], **kwargs):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                sets = update.get("$set", {})
                doc.update(sets)
                return type("Result", (), {"matched_count": 1, "modified_count": 1})()
        return type("Result", (), {"matched_count": 0, "modified_count": 0})()

    async def create_index(self, *args, **kwargs):
        return None


class FakeDB:
    def __init__(self, collections: Dict[str, FakeCollection]) -> None:
        self.collections = collections

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


class TestSkillEvalModels:
    def test_old_case_without_skill_eval_remains_readable(self):
        from app.models.eval import EvalCase

        case = EvalCase(
            case_id="case_old",
            name="old",
            input={"prompt": "hello"},
        )
        assert case.skill_eval is None

    def test_skill_eval_config_and_run_snapshot(self):
        from app.models.eval import (
            EvalRunConfig,
            RunSnapshot,
            SkillEvalConfig,
            SkillEvalVariant,
        )

        config = EvalRunConfig(skill_eval={
            "skill_name": "tushare",
            "variant": "no_target_skill",
        })
        snapshot = RunSnapshot(
            dataset_version="1.0.0",
            case_contents={},
            skill_eval=config.skill_eval,
        )
        parsed = SkillEvalConfig(**config.skill_eval)
        assert parsed.skill_name == "tushare"
        assert parsed.variant == SkillEvalVariant.NO_TARGET_SKILL
        assert snapshot.skill_eval == config.skill_eval

    def test_skill_regression_group_model(self):
        from app.models.eval import SkillRegressionGroup

        group = SkillRegressionGroup(
            group_id="sr_test",
            baseline_run_id="run_b",
            candidate_run_id="run_c",
            dataset_id="ds",
            dataset_version="1.0.0",
            skill_name="tushare",
        )
        assert group.status == "pending"
        assert group.critical_cases == []


class TestSkillTraceAdapter:
    def test_route_and_execute_markers(self):
        from app.services.eval.trace_adapter import trace_adapter

        route = trace_adapter.adapt_vibe_event(
            {"type": "skill_route", "data": {"skill": "tushare", "selected": True}},
            "trial_1",
            1,
        )
        execute = trace_adapter.adapt_vibe_event(
            {"type": "skill_execute", "data": {"skill": "tushare", "effective": True}},
            "trial_1",
            2,
        )
        assert route.data["route_selected"] is True
        assert route.data["candidate_skills"] == ["tushare"]
        assert execute.data["skill_effective"] is True
        assert execute.data["skill_name"] == "tushare"


class TestSkillScorers:
    @pytest.mark.asyncio
    async def test_skill_route_scorer_hit_and_silent_bypass(self):
        from app.services.eval.scorers.skill_route_scorer import SkillRouteScorer

        scorer = SkillRouteScorer()
        case_config = {
            "skill_eval": {
                "route_expectation": {
                    "should_trigger": ["tushare"],
                    "should_not_trigger": ["eastmoney"],
                }
            }
        }
        trace = [
            {"event_type": "skill_route", "data": {"skill": "tushare", "selected": True}},
        ]
        result = await scorer.score({}, trace, case_config)
        assert abs(result.score - 2 / 3) < 0.001
        assert result.raw_output["silent_bypass"] == ["tushare"]

        trace.append({"event_type": "skill_execute", "data": {"skill": "tushare"}})
        result = await scorer.score({}, trace, case_config)
        assert result.passed is True
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_skill_execution_scorer_deterministic_asserts(self):
        from app.services.eval.scorers.skill_execution_scorer import SkillExecutionScorer

        scorer = SkillExecutionScorer()
        case_config = {
            "skill_eval": {
                "execution_asserts": {
                    "required_tools": ["get_market_data"],
                    "forbidden_tools": ["bash"],
                    "schema_checks": [{"field": "open", "required": True}],
                }
            }
        }
        trial_data = {"output_data": {"open": 10.0}}
        trace = [
            {"event_type": "tool_call", "data": {"tool": "get_market_data", "arguments": {"codes": ["600519.SS"]}}},
        ]
        result = await scorer.score(trial_data, trace, case_config)
        assert result.passed is True

        trace = [
            {"event_type": "tool_call", "data": {"tool": "bash", "arguments": {}}},
        ]
        result = await scorer.score({}, trace, case_config)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_skill_coexistence_scorer_metrics(self):
        from app.services.eval.scorers.skill_coexistence_scorer import SkillCoexistenceScorer

        scorer = SkillCoexistenceScorer()
        case_config = {
            "skill_eval": {
                "skill_name": "yfinance",
                "coexistence": {
                    "neighbor_skills": ["okx-market"],
                    "max_neighbor_success_drop": 0.05,
                },
            }
        }
        trial_data = {
            "coexistence": {
                "baseline_neighbor_success": {"okx-market": 0.9},
                "candidate_neighbor_success": {"okx-market": 0.7},
            }
        }
        result = await scorer.score(trial_data, [], case_config)
        assert result.passed is False
        assert "okx-market" in result.raw_output["checks"][0]["name"]


class TestSkillsLoaderFiltering:
    def test_exclude_and_include_skills(self, tmp_path):
        from src.agent.skills import SkillsLoader

        for name in ("alpha", "beta", "gamma"):
            skill_dir = tmp_path / name
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\n---\nbody",
                encoding="utf-8",
            )

        loader = SkillsLoader(skills_dir=tmp_path, exclude_skills={"beta"})
        assert {s.name for s in loader.skills} == {"alpha", "gamma"}
        loader = SkillsLoader(skills_dir=tmp_path, include_skills={"beta"})
        assert {s.name for s in loader.skills} == {"beta"}


class TestRunnerSkillVariant:
    def test_session_config_variants(self):
        from app.services.eval.runner_service import EvalRunnerService

        runner = EvalRunnerService()
        base = {"skill_eval": {"skill_name": "tushare", "variant": "no_target_skill"}}
        no_target = runner._session_config_for_trial(base, None)
        assert no_target["skill_eval"]["exclude_skills"] == ["tushare"]

        only = runner._session_config_for_trial(
            {"skill_eval": {"skill_name": "tushare", "variant": "skill_only"}},
            None,
        )
        assert only["skill_eval"]["include_skills"] == ["tushare"]

    @pytest.mark.asyncio
    async def test_create_run_snapshots_skill_eval(self):
        from app.services.eval.runner_service import runner_service

        case = {
            "case_id": "case_1",
            "name": "skill case",
            "input": {"prompt": "test"},
            "scoring_criteria": {},
            "skill_eval": {"skill_name": "tushare", "critical": True},
            "tags": [],
            "difficulty": "medium",
            "category": "skill",
        }
        db = FakeDB({})
        with patch(
            "app.services.eval.runner_service.dataset_service.get_dataset",
            AsyncMock(return_value={"dataset_id": "ds_1", "version": "1.0.0"}),
        ), patch(
            "app.services.eval.runner_service.dataset_service.list_cases",
            AsyncMock(return_value=[case]),
        ), patch(
            "app.services.eval.runner_service.get_mongo_db",
            return_value=db,
        ):
            result = await runner_service.create_run(
                dataset_id="ds_1",
                num_trials=1,
                config={"skill_eval": {"skill_name": "tushare", "variant": "no_target_skill"}},
            )
            assert result["run_id"]
            inserted = db["eval_runs"].docs[0]
            assert inserted["snapshot"]["skill_eval"]["variant"] == "no_target_skill"
            assert inserted["snapshot"]["case_contents"]["case_1"]["skill_eval"]["skill_name"] == "tushare"


class TestGoldenSkillDataset:
    def test_skill_golden_cases_have_route_and_execution_asserts(self):
        path = Path("app/services/eval/data/skill_golden_cases.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["cases"]) >= 10
        for case in data["cases"]:
            skill_eval = case["skill_eval"]
            assert "route_expectation" in skill_eval
            assert "execution_asserts" in skill_eval


class TestSkillRegressionService:
    @pytest.mark.asyncio
    async def test_create_compute_and_gate(self):
        from app.models.eval import SkillRegressionGroup
        from app.services.eval.skill_regression_service import skill_regression_service

        baseline = {
            "run_id": "run_b",
            "dataset_id": "ds_1",
            "dataset_version": "1.0.0",
            "status": "completed",
        }
        candidate = {
            "run_id": "run_c",
            "dataset_id": "ds_1",
            "dataset_version": "1.0.0",
            "status": "completed",
            "config": {
                "skill_eval": {
                    "skill_name": "tushare",
                    "skill_versions": {"baseline": "1.0.0", "candidate": "1.1.0"},
                }
            },
        }
        critical_case = {
            "case_id": "case_critical",
            "skill_eval": {"critical": True},
        }
        baseline_trials = [
            {
                "trial_id": "trial_b1",
                "run_id": "run_b",
                "case_id": "case_critical",
                "status": "completed",
                "case_snapshot": {"name": "critical"},
            }
        ]
        candidate_trials = [
            {
                "trial_id": "trial_c1",
                "run_id": "run_c",
                "case_id": "case_critical",
                "status": "completed",
                "case_snapshot": {"name": "critical"},
            }
        ]
        baseline_scores = [
            {
                "score_id": "s_b1",
                "trial_id": "trial_b1",
                "score_name": "skill_execution",
                "score": 0.9,
                "passed": True,
                "status": "passed",
                "scorer_version": "1.0.0",
            }
        ]
        candidate_scores = [
            {
                "score_id": "s_c1",
                "trial_id": "trial_c1",
                "score_name": "skill_execution",
                "score": 0.4,
                "passed": False,
                "status": "failed",
                "scorer_version": "1.0.0",
            }
        ]
        db = FakeDB({
            "eval_runs": FakeCollection([baseline, candidate]),
            "eval_trials": FakeCollection(baseline_trials + candidate_trials),
            "eval_scores": FakeCollection(baseline_scores + candidate_scores),
        })
        with patch(
            "app.services.eval.skill_regression_service.get_mongo_db",
            return_value=db,
        ), patch(
            "app.services.eval.dataset_service.dataset_service.list_cases",
            AsyncMock(return_value=[critical_case]),
        ):
            group = await skill_regression_service.create_group("run_b", "run_c", "tester")
            assert isinstance(group, SkillRegressionGroup)
            assert group.critical_cases == ["case_critical"]

            group = await skill_regression_service.compute_deltas(group.group_id)
            assert group.per_case_deltas[0].regressed is True

            group = await skill_regression_service.evaluate_gate(group.group_id)
            assert group.gate_result is not None
            assert group.gate_result.passed is False
            assert any(block["name"] == "critical_case_regression" for block in group.gate_result.blocks)

            group = await skill_regression_service.override_group(
                group.group_id,
                allowed=True,
                reason="manual pass",
                overridden_by="admin",
            )
            assert group.gate_result.passed is True
            assert group.override["allowed"] is True


class TestEvolutionSkillRegressionIntegration:
    @pytest.mark.asyncio
    async def test_verification_comparison_consumes_skill_regression_group(self):
        from app.models.eval import (
            SkillCaseDelta,
            SkillRegressionGateResult,
            SkillRegressionGroup,
        )
        from app.services.evolution.verification_service import VerificationService

        group = SkillRegressionGroup(
            group_id="sr_integration",
            baseline_run_id="run_b",
            candidate_run_id="run_c",
            dataset_id="ds",
            dataset_version="1.0.0",
            skill_name="tushare",
            per_case_deltas=[
                SkillCaseDelta(
                    case_id="case_1",
                    critical=True,
                    regressed=True,
                    regressed_dimensions=["skill_execution"],
                    dimension_deltas={"skill_execution": -0.2},
                )
            ],
            gate_result=SkillRegressionGateResult(
                passed=False,
                blocks=[{"name": "critical_case_regression"}],
            ),
        )
        with patch(
            "app.services.eval.skill_regression_service.skill_regression_service.get_group",
            AsyncMock(return_value=group),
        ):
            metrics = MagicMock()
            metrics.compare_runs = AsyncMock(return_value={"runs": []})
            metrics.compute_pass_at_k = AsyncMock(return_value={})
            metrics.get_score_aggregation = AsyncMock(return_value={"scores": {}})
            comparison = await VerificationService()._compute_comparison(
                "run_b",
                "run_c",
                metrics,
                skill_regression_group_id="sr_integration",
            )
        assert comparison["new_regressions"]
        assert comparison["skill_regression_gate"]["passed"] is False
        assert comparison["gate"]["passed"] is False

    def test_promote_regression_gate_and_override(self):
        from app.services.evolution.promote_service import PromoteService

        service = PromoteService()
        comparison = {
            "skill_regression_group_id": "sr_1",
            "skill_regression_gate": {"passed": False},
        }
        with pytest.raises(ValueError, match="Skill regression gate"):
            service._resolve_skill_regression_gate(
                comparison,
                required=True,
                override_allowed=False,
                allow_override=False,
                promoted_by="admin",
            )
        group_id, gate, override = service._resolve_skill_regression_gate(
            comparison,
            required=True,
            override_allowed=True,
            allow_override=True,
            promoted_by="admin",
        )
        assert group_id == "sr_1"
        assert override["allowed"] is True
        assert override["overridden_by"] == "admin"

    def test_skill_regression_api_routes_registered(self):
        from app.routers.eval import router

        paths = {route.path for route in router.routes}
        assert "/skill-regression-groups" in paths
        assert "/skill-regression-groups/{group_id}/gate" in paths
