"""观察标的新闻影响分析测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.news_watch_service import NewsWatchService


class TestNewsStockImpact:
    @pytest.mark.asyncio
    async def test_analyze_stock_impact_uses_symbol_and_profile(self):
        service = NewsWatchService()
        mock_db = MagicMock()
        mock_db["investment_profiles"].find_one = AsyncMock(return_value={
            "user_id": "u1",
            "risk_preference": "conservative",
        })
        mock_db["stock_basic_info"].find_one = AsyncMock(return_value={
            "code": "600519",
            "name": "贵州茅台",
        })

        news_service = MagicMock()
        news_service.query_news = AsyncMock(return_value=[
            {"title": "重要公告", "sentiment": "positive", "importance": "high", "publish_time": "2026-08-31T10:00:00Z"},
            {"title": "业绩增长", "sentiment": "positive", "importance": "medium", "publish_time": "2026-08-31T09:00:00Z"},
            {"title": "机构增持", "sentiment": "positive", "importance": "medium", "publish_time": "2026-08-31T08:00:00Z"},
        ])

        service._db = mock_db
        with patch(
            "app.services.news_data_service.get_news_data_service",
            new=AsyncMock(return_value=news_service),
        ):
            result = await service.analyze_stock_impact("u1", "600519", hours_back=72)

        assert result["symbol"] == "600519"
        assert result["holdings_count"] == 1
        assert result["impacts"][0]["stock_name"] == "贵州茅台"
        assert result["impacts"][0]["news_count"] == 3
        assert result["data_sufficient"] is True
