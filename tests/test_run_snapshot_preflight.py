"""Run snapshot 契约与 preflight 测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.eval import RunStatus
from app.services.eval.runner_service import (
    CaseSnapshotValidationError,
    runner_service,
)


@pytest.mark.asyncio
async def test_resolve_run_cases_fills_case_id_from_snapshot_key():
    run_doc = {
        "snapshot": {
            "case_contents": {
                "case_1": {"input": {"prompt": "prompt-1"}},
            }
        }
    }
    cases = await runner_service._resolve_run_cases(run_doc, "ds_1", "1.0.0")
    assert cases[0]["case_id"] == "case_1"
    assert cases[0]["input"]["prompt"] == "prompt-1"


@pytest.mark.asyncio
async def test_resolve_run_cases_raises_when_case_id_cannot_be_recovered():
    run_doc = {
        "snapshot": {
            "case_contents": {
                "": {"input": {"prompt": "prompt-1"}},
            }
        }
    }
    with pytest.raises(CaseSnapshotValidationError):
        await runner_service._resolve_run_cases(run_doc, "ds_1", "1.0.0")


@pytest.mark.asyncio
async def test_preflight_passes_for_valid_snapshot():
    run_doc = {
        "snapshot": {
            "case_contents": {
                "case_1": {
                    "case_id": "case_1",
                    "input": {"prompt": "prompt-1"},
                }
            }
        },
        "total_cases": 1,
        "config": {"timeout_seconds": 30},
    }
    result = await runner_service._preflight_run(run_doc)
    assert result["status"] == "passed"
    assert result["checked_cases"] == 1
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_preflight_fails_on_case_count_mismatch():
    run_doc = {
        "snapshot": {
            "case_contents": {
                "case_1": {
                    "case_id": "case_1",
                    "input": {"prompt": "prompt-1"},
                }
            }
        },
        "total_cases": 3,
        "config": {},
    }
    result = await runner_service._preflight_run(run_doc)
    assert result["status"] == "failed"
    assert any("case count mismatch" in error for error in result["errors"])
    assert result["error_code"] == "RUN_PREFLIGHT_FAILED"


@pytest.mark.asyncio
async def test_start_run_marks_failed_run_when_preflight_fails():
    run_doc = {
        "run_id": "run_fail",
        "status": RunStatus.PENDING.value,
        "snapshot": {"case_contents": {}},
        "total_cases": 0,
        "config": {},
    }
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=run_doc)
    collection.update_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection

    with patch("app.services.eval.runner_service.get_mongo_db", return_value=db):
        result = await runner_service.start_run("run_fail")

    assert result["started"] is False
    assert result["status"] == RunStatus.FAILED.value
    assert result["preflight"]["status"] == "failed"
    collection.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_create_run_writes_case_id_into_snapshot_values():
    from app.services.eval.dataset_service import dataset_service

    async def fake_get_dataset(dataset_id: str):
        return {"dataset_id": dataset_id, "version": "1.0.0"}

    async def fake_list_cases(*args, **kwargs):
        return [
            {
                "case_id": "case_1",
                "name": "case-1",
                "input": {"prompt": "prompt-1"},
                "expected_output": None,
                "scoring_criteria": {},
                "tags": [],
                "difficulty": "medium",
                "category": "general",
            }
        ]

    collection = MagicMock()
    collection.insert_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection

    with (
        patch("app.services.eval.runner_service.get_mongo_db", return_value=db),
        patch.object(dataset_service, "get_dataset", side_effect=fake_get_dataset),
        patch.object(dataset_service, "list_cases", side_effect=fake_list_cases),
    ):
        await runner_service.create_run("ds_1")

    inserted = collection.insert_one.call_args[0][0]
    case_value = inserted["snapshot"]["case_contents"]["case_1"]
    assert case_value["case_id"] == "case_1"


@pytest.mark.asyncio
async def test_create_run_with_63_cases_has_matching_preflight():
    from app.services.eval.dataset_service import dataset_service

    async def fake_get_dataset(dataset_id: str):
        return {"dataset_id": dataset_id, "version": "1.0.21"}

    async def fake_list_cases(*args, **kwargs):
        return [
            {
                "case_id": f"case_{index}",
                "name": f"case-{index}",
                "input": {"prompt": f"prompt-{index}"},
                "expected_output": None,
                "scoring_criteria": {},
                "tags": [],
                "difficulty": "medium",
                "category": "general",
            }
            for index in range(63)
        ]

    collection = MagicMock()
    collection.insert_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection

    with (
        patch("app.services.eval.runner_service.get_mongo_db", return_value=db),
        patch.object(dataset_service, "get_dataset", side_effect=fake_get_dataset),
        patch.object(dataset_service, "list_cases", side_effect=fake_list_cases),
    ):
        result = await runner_service.create_run("ds_e2f3ca922896")

    inserted = collection.insert_one.call_args[0][0]
    assert result["total_cases"] == 63
    assert len(inserted["snapshot"]["case_contents"]) == 63
    preflight = await runner_service._preflight_run(inserted)
    assert preflight["status"] == "passed"
    assert preflight["checked_cases"] == 63


@pytest.mark.asyncio
async def test_execute_run_creates_trial_for_valid_snapshot():
    run_doc = {
        "run_id": "run_ok",
        "total_cases": 1,
        "num_trials_per_case": 1,
        "dataset_id": "ds_1",
        "dataset_version": "1.0.0",
        "config": {"timeout_seconds": 30},
        "snapshot": {
            "case_contents": {
                "case_1": {
                    "case_id": "case_1",
                    "input": {"prompt": "prompt-1"},
                    "name": "case-1",
                    "expected_output": None,
                    "scoring_criteria": {},
                }
            }
        },
    }
    run_collection = MagicMock()
    run_collection.find_one = AsyncMock(return_value=run_doc)
    run_collection.update_one = AsyncMock()
    trial_collection = MagicMock()
    trial_collection.insert_one = AsyncMock()
    trial_collection.count_documents = AsyncMock(side_effect=[1, 0])
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: (
        run_collection if name == runner_service.COLLECTION_RUNS else trial_collection
    )

    with patch("app.services.eval.runner_service.get_mongo_db", return_value=db):
        with patch.object(
            runner_service,
            "_execute_trial",
            new=AsyncMock(),
        ):
            await runner_service._execute_run("run_ok")

    trial_collection.insert_one.assert_called_once()
    assert run_collection.update_one.call_args[0][1]["$set"]["completed_trials"] == 1
