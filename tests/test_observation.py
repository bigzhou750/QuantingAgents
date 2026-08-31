"""
投资观察标的服务测试

覆盖:
- 模型序列化
- 用户隔离
- CRUD 操作
- 状态更新（REMOVED 非删除）
- 重复添加处理（ACTIVE 返回已有，REMOVED 重新激活）
- 复盘备注
- 待复盘汇总
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.observation import (
    ObservationRecord,
    ObservationStatus,
    ObservationSource,
    ReviewNote,
    ReviewTargetType,
)
from app.services.personal_investment.observation_service import ObservationService


# ==================== 模型测试 ====================

class TestObservationModels:
    """测试 Pydantic 模型"""

    def test_observation_record_defaults(self):
        record = ObservationRecord(user_id="u1", stock_code="000001")
        assert record.status == ObservationStatus.ACTIVE.value
        assert record.source_type == ObservationSource.MANUAL.value
        assert record.market == "CN"
        assert record.match_reasons == []
        assert record.risk_warnings == []

    def test_observation_record_to_doc(self):
        record = ObservationRecord(
            user_id="u1",
            stock_code="600519",
            stock_name="贵州茅台",
            source_type=ObservationSource.SCREENING.value,
            match_reasons=["ROE > 15%", "PE < 20"],
        )
        doc = record.to_doc()
        assert doc["stock_code"] == "600519"
        assert doc["stock_name"] == "贵州茅台"
        assert len(doc["match_reasons"]) == 2
        assert "observation_id" in doc
        assert doc["observation_id"] != ""

    def test_review_note_to_doc(self):
        note = ReviewNote(
            user_id="u1",
            target_id="obs_123",
            content="判断正确，趋势延续",
        )
        doc = note.to_doc()
        assert doc["target_type"] == ReviewTargetType.OBSERVATION.value
        assert doc["note_id"] != ""
        assert doc["content"] == "判断正确，趋势延续"

    def test_enums_values(self):
        assert ObservationSource.SCREENING.value == "screening"
        assert ObservationSource.MANUAL.value == "manual"
        assert ObservationStatus.ACTIVE.value == "active"
        assert ObservationStatus.REMOVED.value == "removed"
        assert ObservationStatus.REVIEWED.value == "reviewed"


# ==================== Service 测试（mock DB）====================

class TestObservationService:
    @pytest.fixture
    def service(self):
        return ObservationService()

    def _make_mock_db(self):
        mock_db = MagicMock()
        mock_coll_obs = AsyncMock()
        mock_coll_notes = AsyncMock()

        def getitem(name):
            if name == "investment_observations":
                return mock_coll_obs
            return mock_coll_notes

        mock_db.__getitem__ = MagicMock(side_effect=getitem)
        return mock_db, mock_coll_obs, mock_coll_notes

    @pytest.mark.asyncio
    async def test_add_observation_new(self, service):
        """新建观察标的"""
        mock_db, mock_coll, _ = self._make_mock_db()
        mock_coll.find_one = AsyncMock(return_value=None)
        mock_coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id="oid"))

        record = ObservationRecord(user_id="u1", stock_code="000001", stock_name="平安银行")

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.add_observation("u1", record)

        assert result["stock_code"] == "000001"
        assert result["stock_name"] == "平安银行"
        mock_coll.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_observation_duplicate_active(self, service):
        """已存在 ACTIVE 记录时直接返回"""
        mock_db, mock_coll, _ = self._make_mock_db()
        existing = {
            "_id": "existing_oid",
            "user_id": "u1",
            "stock_code": "000001",
            "status": "active",
            "stock_name": "平安银行",
        }
        mock_coll.find_one = AsyncMock(return_value=existing)

        record = ObservationRecord(user_id="u1", stock_code="000001")

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.add_observation("u1", record)

        assert result["stock_code"] == "000001"
        mock_coll.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_observation_reactivate_removed(self, service):
        """之前 REMOVED 的记录重新激活"""
        mock_db, mock_coll, _ = self._make_mock_db()
        existing = {
            "_id": "old_oid",
            "user_id": "u1",
            "stock_code": "000001",
            "status": "removed",
            "stock_name": "平安银行",
        }
        mock_coll.find_one = AsyncMock(return_value=existing)
        mock_coll.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        # 第二次 find_one 返回更新后的文档
        updated_doc = {**existing, "status": "active"}
        mock_coll.find_one = AsyncMock(side_effect=[existing, updated_doc])

        record = ObservationRecord(
            user_id="u1",
            stock_code="000001",
            source_type="screening",
            match_reasons=["新原因"],
        )

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.add_observation("u1", record)

        mock_coll.update_one.assert_called_once()
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_remove_observation_status_update(self, service):
        """移出观察是状态更新而非删除"""
        mock_db, mock_coll, _ = self._make_mock_db()
        mock_coll.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            success = await service.remove_observation("obs_123", "u1")

        assert success is True
        call_args = mock_coll.update_one.call_args
        assert call_args[0][1]["$set"]["status"] == "removed"

    @pytest.mark.asyncio
    async def test_remove_observation_not_found(self, service):
        """移出不存在的观察返回 False"""
        mock_db, mock_coll, _ = self._make_mock_db()
        mock_coll.update_one = AsyncMock(return_value=MagicMock(modified_count=0))

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            success = await service.remove_observation("nonexistent", "u1")

        assert success is False

    @pytest.mark.asyncio
    async def test_is_observing(self, service):
        """检查是否正在观察"""
        mock_db, mock_coll, _ = self._make_mock_db()
        mock_coll.find_one = AsyncMock(return_value={"_id": "x"})

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.is_observing("u1", "000001")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_not_observing(self, service):
        mock_db, mock_coll, _ = self._make_mock_db()
        mock_coll.find_one = AsyncMock(return_value=None)

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.is_observing("u1", "999999")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_observations_user_isolation(self, service):
        """列表查询必须包含 user_id"""
        mock_db, mock_coll, _ = self._make_mock_db()
        mock_coll.count_documents = AsyncMock(return_value=0)

        async def empty_cursor(*args, **kwargs):
            return
            yield  # make it an async generator

        mock_coll.find = MagicMock(return_value=MagicMock(
            sort=MagicMock(return_value=MagicMock(
                skip=MagicMock(return_value=MagicMock(
                    limit=MagicMock(return_value=empty_cursor())
                ))
            ))
        ))

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            await service.list_observations("u1")

        # 验证查询条件包含 user_id
        call_args = mock_coll.find.call_args[0][0]
        assert call_args["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_add_review_note(self, service):
        """添加复盘备注"""
        mock_db, mock_coll_obs, mock_coll_notes = self._make_mock_db()
        mock_coll_notes.insert_one = AsyncMock(return_value=MagicMock(inserted_id="note_oid"))
        mock_coll_obs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.add_review_note("u1", "obs_123", "判断正确")

        assert result["content"] == "判断正确"
        assert result["target_id"] == "obs_123"
        # 验证观察状态更新为 reviewed
        mock_coll_obs.update_one.assert_called_once()
        obs_update = mock_coll_obs.update_one.call_args[0][1]["$set"]
        assert obs_update["status"] == "reviewed"

    @pytest.mark.asyncio
    async def test_get_pending_reviews_empty(self, service):
        """无活跃观察时待复盘为空"""
        mock_db, mock_coll, _ = self._make_mock_db()

        async def empty_async_cursor(*args, **kwargs):
            return
            yield

        mock_coll.find = MagicMock(return_value=empty_async_cursor())

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.get_pending_reviews("u1")

        assert result["count"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_source_fields_preserved(self, service):
        """来源字段在创建时被正确保存"""
        mock_db, mock_coll, _ = self._make_mock_db()
        mock_coll.find_one = AsyncMock(return_value=None)
        mock_coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id="oid"))

        record = ObservationRecord(
            user_id="u1",
            stock_code="600519",
            source_type=ObservationSource.SCREENING.value,
            source_strategy_id="tpl_abc",
            source_task_id="task_xyz",
            match_reasons=["ROE高", "估值低"],
            risk_warnings=["行业集中度高"],
        )

        with patch("app.services.personal_investment.observation_service.get_mongo_db", return_value=mock_db):
            result = await service.add_observation("u1", record)

        assert result["source_strategy_id"] == "tpl_abc"
        assert result["source_task_id"] == "task_xyz"
        assert len(result["match_reasons"]) == 2
        assert len(result["risk_warnings"]) == 1
