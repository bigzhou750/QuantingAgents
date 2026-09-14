"""线上 Bad Case 配置服务测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.eval import OnlineBadcaseConfigStatus
from app.services.eval.online_badcase_config_service import (
    online_badcase_config_service,
    validate_config,
)


def test_validate_config_rejects_out_of_range_values():
    with pytest.raises(ValueError):
        validate_config({"soft_sample_rate": 1.2})
    with pytest.raises(ValueError):
        validate_config({"max_content_length": 1})


@pytest.mark.asyncio
async def test_create_draft_inserts_draft_with_next_version():
    collection = MagicMock()
    collection.count_documents = AsyncMock(return_value=0)
    collection.insert_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection

    service = online_badcase_config_service
    service._initialized = True
    service.invalidate_cache()
    with patch(
        "app.services.eval.online_badcase_config_service.get_mongo_db",
        return_value=db,
    ):
        draft = await service.create_draft(
            {
                "enabled": True,
                "soft_sample_rate": 0.2,
                "change_reason": "test",
            },
            updated_by="admin",
        )

    assert draft["version"] == 1
    assert draft["status"] == OnlineBadcaseConfigStatus.DRAFT.value
    assert draft["enabled"] is True


@pytest.mark.asyncio
async def test_publish_archives_previous_published_config():
    target = {
        "config_id": "cfg_2",
        "config_key": "default",
        "version": 2,
        "enabled": True,
        "enable_judge": False,
        "soft_sample_rate": 0.2,
        "confidence_threshold": 0.8,
        "judge_threshold": 0.6,
        "evidence_threshold": 0.6,
        "max_content_length": 5000,
        "status": OnlineBadcaseConfigStatus.DRAFT.value,
        "source": "db",
        "updated_by": "admin",
        "updated_at": "2026-09-11T00:00:00+00:00",
        "change_reason": "",
    }
    updated = {**target, "status": OnlineBadcaseConfigStatus.PUBLISHED.value}
    collection = MagicMock()
    collection.find_one = AsyncMock(side_effect=[target, updated])
    collection.update_many = AsyncMock()
    collection.update_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection

    service = online_badcase_config_service
    service._initialized = True
    service.invalidate_cache()
    with patch(
        "app.services.eval.online_badcase_config_service.get_mongo_db",
        return_value=db,
    ):
        published = await service.publish("cfg_2", updated_by="admin")

    assert published["status"] == OnlineBadcaseConfigStatus.PUBLISHED.value
    collection.update_many.assert_called_once()
    service._last_valid_config = None


@pytest.mark.asyncio
async def test_get_effective_config_uses_cache():
    collection = MagicMock()
    collection.find_one = AsyncMock(
        return_value={
            "config_id": "cfg_1",
            "config_key": "default",
            "version": 1,
            "enabled": True,
            "enable_judge": False,
            "soft_sample_rate": 0.3,
            "confidence_threshold": 0.8,
            "judge_threshold": 0.6,
            "evidence_threshold": 0.6,
            "max_content_length": 5000,
            "status": OnlineBadcaseConfigStatus.PUBLISHED.value,
            "source": "db",
            "updated_by": "admin",
            "updated_at": "2026-09-11T00:00:00+00:00",
            "change_reason": "",
        }
    )
    db = MagicMock()
    db.__getitem__.return_value = collection

    service = online_badcase_config_service
    service._initialized = True
    service.invalidate_cache()
    service._last_valid_config = None
    with patch(
        "app.services.eval.online_badcase_config_service.get_mongo_db",
        return_value=db,
    ):
        first = await service.get_effective_config()
        second = await service.get_effective_config()

    assert first["enabled"] is True
    assert first["soft_sample_rate"] == 0.3
    assert second is first
    assert collection.find_one.await_count == 1


@pytest.mark.asyncio
async def test_get_effective_config_fails_closed_when_read_fails():
    collection = MagicMock()
    collection.find_one = AsyncMock(side_effect=RuntimeError("db down"))
    db = MagicMock()
    db.__getitem__.return_value = collection

    service = online_badcase_config_service
    service._initialized = True
    service.invalidate_cache()
    service._last_valid_config = None
    with patch(
        "app.services.eval.online_badcase_config_service.get_mongo_db",
        return_value=db,
    ):
        config = await service.get_effective_config()

    assert config["enabled"] is False
    assert config["source"] == "fail_closed"
