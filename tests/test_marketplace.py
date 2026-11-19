"""
策略广场测试

覆盖:
- StrategyTemplate 模型序列化
- TemplateStatus / TemplateSource 枚举
- MarketplaceService 核心逻辑（mock Mongo）
- 合规检查拦截
- adopt_template 重复检测
- seed_builtin_templates 幂等性
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.personal_investment import (
    StrategyTemplate,
    TemplateStatus,
    TemplateSource,
)
from app.services.personal_investment.marketplace_service import marketplace_service


# ==================== 模型测试 ====================

class TestStrategyTemplateModel:
    """StrategyTemplate 模型测试"""

    def test_create_minimal(self):
        tpl = StrategyTemplate(template_id="tpl_test001", name="测试策略")
        assert tpl.template_id == "tpl_test001"
        assert tpl.name == "测试策略"
        assert tpl.status == TemplateStatus.DRAFT
        assert tpl.source == TemplateSource.BUILTIN
        assert tpl.version == "1.0.0"
        assert tpl.one_liner == ""
        assert tpl.audience == ""
        assert tpl.not_for == ""
        assert tpl.risk_boundary == ""
        assert tpl.rule_explanation == {}
        assert tpl.screening_criteria == {}
        assert tpl.tags == []
        assert tpl.applicable_markets == ["A股"]

    def test_create_full(self):
        tpl = StrategyTemplate(
            template_id="tpl_full001",
            name="完整策略",
            one_liner="一句话说明",
            description="详细描述",
            status=TemplateStatus.PUBLISHED,
            source=TemplateSource.OPERATIONS,
            version="2.1.0",
            author="admin",
            audience="适合新手",
            not_for="不适合激进投资者",
            risk_boundary="可能亏损20%",
            data_requirements="需要财务数据",
            rule_explanation={"pe_max": "市盈率上限"},
            applicable_markets=["A股", "港股"],
            screening_criteria={"pe_max": 20, "roe_min": 8},
            parameters={"rebalance_days": 30},
            tags=["value", "dividend"],
        )
        assert tpl.status == TemplateStatus.PUBLISHED
        assert tpl.source == TemplateSource.OPERATIONS
        assert tpl.rule_explanation["pe_max"] == "市盈率上限"
        assert tpl.screening_criteria["pe_max"] == 20
        assert len(tpl.tags) == 2

    def test_serialization_roundtrip(self):
        tpl = StrategyTemplate(
            template_id="tpl_ser001",
            name="序列化测试",
            status=TemplateStatus.PUBLISHED,
            screening_criteria={"pe_max": 15},
            tags=["value"],
        )
        data = tpl.model_dump(by_alias=True, exclude={"id"})
        restored = StrategyTemplate(**data)
        assert restored.template_id == tpl.template_id
        assert restored.status == tpl.status
        assert restored.screening_criteria == tpl.screening_criteria

    def test_name_max_length(self):
        with pytest.raises(Exception):
            StrategyTemplate(template_id="tpl_long", name="x" * 101)

    def test_one_liner_max_length(self):
        with pytest.raises(Exception):
            StrategyTemplate(template_id="tpl_ol", name="ok", one_liner="x" * 201)


class TestTemplateEnums:
    """模板相关枚举测试"""

    def test_template_status_values(self):
        assert TemplateStatus.DRAFT.value == "draft"
        assert TemplateStatus.PENDING_REVIEW.value == "pending_review"
        assert TemplateStatus.PUBLISHED.value == "published"
        assert TemplateStatus.REJECTED.value == "rejected"
        assert TemplateStatus.DISABLED.value == "disabled"

    def test_template_source_values(self):
        assert TemplateSource.BUILTIN.value == "builtin"
        assert TemplateSource.OPERATIONS.value == "operations"
        assert TemplateSource.AGENT_DRAFT.value == "agent_draft"


# ==================== Service 测试（mock Mongo）====================

class TestMarketplaceService:
    """MarketplaceService 单元测试"""

    @pytest.fixture
    def service(self):
        from app.services.personal_investment.marketplace_service import MarketplaceService
        svc = MarketplaceService()
        return svc

    @pytest.mark.asyncio
    async def test_list_published_templates(self, service):
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_collection.count_documents = AsyncMock(return_value=2)

        fake_docs = [
            {"template_id": "tpl_a", "name": "A", "status": "published", "_id": "oid1"},
            {"template_id": "tpl_b", "name": "B", "status": "published", "_id": "oid2"},
        ]

        async def fake_cursor():
            for doc in fake_docs:
                yield doc

        mock_collection.find = MagicMock()
        mock_collection.find.return_value.skip = MagicMock()
        mock_collection.find.return_value.skip.return_value.limit = MagicMock()
        mock_collection.find.return_value.skip.return_value.limit.return_value.sort = MagicMock()
        # Make sort return an async iterable
        sort_result = mock_collection.find.return_value.skip.return_value.limit.return_value.sort.return_value
        sort_result.__aiter__ = lambda self: fake_cursor().__aiter__()
        sort_result.__anext__ = lambda self: fake_cursor().__anext__()

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            result = await service.list_published_templates()

        assert result["count"] == 2
        assert len(result["items"]) == 2
        assert mock_collection.find.call_args[0][0]["status"] == "published"
        # _id should be stripped
        for item in result["items"]:
            assert "_id" not in item

    @pytest.mark.asyncio
    async def test_get_template(self, service):
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        fake_doc = {
            "template_id": "tpl_x",
            "name": "X",
            "one_liner": "关注稳健公司",
            "audience": "适合新手",
            "not_for": "不适合激进者",
            "risk_boundary": "存在回撤风险",
            "data_requirements": "需要财务数据",
            "rule_explanation": {"pe_max": "市盈率上限"},
            "_id": "oid_x",
        }
        mock_collection.find_one = AsyncMock(return_value=fake_doc)

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            result = await service.get_template("tpl_x")

        assert result is not None
        assert result["template_id"] == "tpl_x"
        assert result["rule_explanation"]["pe_max"] == "市盈率上限"
        assert result["risk_boundary"] == "存在回撤风险"
        assert "_id" not in result

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, service):
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find_one = AsyncMock(return_value=None)

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            result = await service.get_template("tpl_nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_adopt_template_duplicate_check(self, service):
        """已加入过的模板应被拒绝"""
        mock_db = MagicMock()
        mock_collection_tpl = AsyncMock()
        mock_collection_strat = AsyncMock()

        def getitem(name):
            if name == "strategy_templates":
                return mock_collection_tpl
            return mock_collection_strat

        mock_db.__getitem__ = MagicMock(side_effect=getitem)

        # Template exists and is published
        mock_collection_tpl.find_one = AsyncMock(return_value={
            "template_id": "tpl_dup",
            "name": "重复策略",
            "status": "published",
            "version": "1.0.0",
        })

        # User already has this template
        mock_collection_strat.find_one = AsyncMock(return_value={
            "strategy_id": "strat_existing",
            "name": "重复策略",
        })

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            with pytest.raises(ValueError, match="已加入过"):
                await service.adopt_template("tpl_dup", "user_001")

        dup_query = mock_collection_strat.find_one.call_args[0][0]
        assert dup_query["user_id"] == "user_001"

    @pytest.mark.asyncio
    async def test_adopt_template_not_published(self, service):
        """未上架的模板不能被加入"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_collection.find_one = AsyncMock(return_value={
            "template_id": "tpl_draft",
            "name": "草稿策略",
            "status": "draft",
        })

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            with pytest.raises(ValueError, match="未上架"):
                await service.adopt_template("tpl_draft", "user_001")

    @pytest.mark.asyncio
    async def test_adopt_template_success_creates_user_strategy(self, service):
        """加入策略应复制模板为用户策略实例并保留来源追踪"""
        mock_db = MagicMock()
        mock_collection_tpl = AsyncMock()
        mock_collection_strat = AsyncMock()

        def getitem(name):
            if name == "strategy_templates":
                return mock_collection_tpl
            return mock_collection_strat

        mock_db.__getitem__ = MagicMock(side_effect=getitem)
        mock_collection_tpl.find_one = AsyncMock(return_value={
            "template_id": "tpl_ok",
            "name": "低估值红利策略",
            "description": "估值与分红筛选",
            "status": "published",
            "version": "1.2.0",
            "applicable_markets": ["A股"],
            "screening_criteria": {"pe_max": 20},
            "parameters": {"rebalance_days": 30},
            "tags": ["value"],
        })
        mock_collection_strat.find_one = AsyncMock(return_value=None)
        mock_collection_strat.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        from app.services.personal_investment.strategy_service import strategy_service
        with patch(
            "app.services.personal_investment.strategy_service.strategy_service.create_strategy",
            new=AsyncMock(return_value={"strategy_id": "strat_new", "name": "低估值红利策略"}),
        ):
            with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
                result = await service.adopt_template("tpl_ok", "user_001")

        assert result["strategy_id"] == "strat_new"
        assert result["source_template_id"] == "tpl_ok"
        update_args = mock_collection_strat.update_one.call_args
        assert update_args[0][0] == {"strategy_id": "strat_new", "user_id": "user_001"}
        assert update_args[0][1]["$set"]["source_template_id"] == "tpl_ok"
        assert update_args[0][1]["$set"]["source_template_version"] == "1.2.0"
        assert update_args[0][1]["$set"]["source_type"] == "marketplace"

    @pytest.mark.asyncio
    async def test_seed_builtin_templates_idempotent(self, service):
        """种子数据插入应是幂等的"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        # Simulate already seeded
        mock_collection.count_documents = AsyncMock(return_value=3)

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            await service.seed_builtin_templates()

        # Should NOT have called insert_one since count > 0
        mock_collection.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_seed_builtin_templates_inserts(self, service):
        """首次运行时应插入3条种子数据"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_collection.insert_one = AsyncMock()

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            await service.seed_builtin_templates()

        assert mock_collection.insert_one.call_count == 3
        # Verify template IDs
        inserted_ids = [
            call.args[0]["template_id"]
            for call in mock_collection.insert_one.call_args_list
        ]
        assert "tpl_value_dividend" in inserted_ids
        assert "tpl_growth_momentum" in inserted_ids
        assert "tpl_balanced_start" in inserted_ids
        for call in mock_collection.insert_one.call_args_list:
            doc = call.args[0]
            assert doc["one_liner"]
            assert doc["audience"]
            assert doc["risk_boundary"]
            assert doc["data_requirements"]
            assert doc["rule_explanation"]

    @pytest.mark.asyncio
    async def test_create_template_compliance_reject(self, service):
        """包含违禁词的模板应被拒绝"""
        with patch("app.services.personal_investment.marketplace_service.get_mongo_db"):
            with pytest.raises(ValueError, match="不合规措辞"):
                await service.create_template(
                    name="保证收益策略",
                    one_liner="稳赚不赔",
                    description="这个策略能保证盈利",
                    auto_publish=True,
                )

    @pytest.mark.asyncio
    async def test_create_template_agent_draft_cannot_auto_publish(self, service):
        """Agent 生成策略不得直接上架"""
        with patch("app.services.personal_investment.marketplace_service.get_mongo_db"):
            with pytest.raises(ValueError, match="不能直接上架"):
                await service.create_template(
                    name="Agent 研究策略",
                    one_liner="关注稳健公司",
                    audience="新手",
                    risk_boundary="存在回撤风险",
                    data_requirements="需要财务数据",
                    rule_explanation={"pe_max": "市盈率上限"},
                    source=TemplateSource.AGENT_DRAFT,
                    auto_publish=True,
                )

    @pytest.mark.asyncio
    async def test_publish_template_missing_fields_reject(self, service):
        """上架前必须补齐新手解释字段"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find_one = AsyncMock(return_value={
            "template_id": "tpl_short",
            "name": "简单策略",
            "description": "研究优质公司",
            "one_liner": "关注优质公司",
            "status": "draft",
        })

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            with pytest.raises(ValueError, match="缺少上架必填字段"):
                await service.publish_template("tpl_short")

    @pytest.mark.asyncio
    async def test_publish_template_compliance_reject(self, service):
        """上架时也应做合规检查"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_collection.find_one = AsyncMock(return_value={
            "template_id": "tpl_bad",
            "name": "保本策略",
            "description": "保证不亏钱",
            "one_liner": "零风险投资",
            "status": "draft",
            "audience": "适合新手",
            "risk_boundary": "存在市场风险",
            "data_requirements": "需要财务数据",
            "rule_explanation": {"pe_max": "市盈率上限"},
        })

        with patch("app.services.personal_investment.marketplace_service.get_mongo_db", return_value=mock_db):
            with pytest.raises(ValueError, match="不合规措辞"):
                await service.publish_template("tpl_bad")


class TestMarketplaceAPI:
    """策略广场 API 测试"""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers.auth_db import get_current_user
        from app.routers.personal_investment import router

        app = FastAPI()
        app.include_router(router, prefix="/api/investment")
        app.dependency_overrides[get_current_user] = lambda: {"id": "user_001"}
        with TestClient(app) as test_client:
            yield test_client

    def test_list_marketplace_templates(self, client):
        with patch.object(
            marketplace_service,
            "list_published_templates",
            new=AsyncMock(return_value={"items": [{"template_id": "tpl_ok"}], "count": 1}),
        ):
            resp = client.get("/api/investment/marketplace")

        assert resp.status_code == 200
        assert resp.json()["data"]["items"][0]["template_id"] == "tpl_ok"

    def test_get_marketplace_template_hides_non_published(self, client):
        with patch.object(
            marketplace_service,
            "get_template",
            new=AsyncMock(return_value={"template_id": "tpl_draft", "status": "draft"}),
        ):
            resp = client.get("/api/investment/marketplace/tpl_draft")

        assert resp.status_code == 403

    def test_adopt_template_uses_current_user(self, client):
        adopt_mock = AsyncMock(return_value={"strategy_id": "strat_1", "source_template_id": "tpl_ok"})
        with patch.object(
            marketplace_service,
            "adopt_template",
            new=adopt_mock,
        ):
            resp = client.post("/api/investment/marketplace/tpl_ok/adopt")
            assert resp.status_code == 200
            adopt_mock.assert_awaited_once_with("tpl_ok", "user_001")
