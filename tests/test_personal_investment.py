"""
个人投资助手基础测试

验证数据模型、服务和 API 的基本功能。
"""

import pytest


class TestInvestmentModels:
    """测试数据模型"""

    def test_investment_profile_model(self):
        """测试投资画像模型"""
        from app.models.personal_investment import InvestmentProfile, RiskPreference, TradingStyle

        profile = InvestmentProfile(
            user_id="user_001",
            risk_preference=RiskPreference.BALANCED,
            trading_style=TradingStyle.VALUE,
            capital_range_min=10000,
            capital_range_max=500000,
            target_markets=["A股"],
            exclude_st=True,
        )

        assert profile.user_id == "user_001"
        assert profile.risk_preference == RiskPreference.BALANCED
        assert profile.exclude_st is True

    def test_strategy_definition_model(self):
        """测试策略定义模型"""
        from app.models.personal_investment import StrategyDefinition, StrategyStatus

        strategy = StrategyDefinition(
            strategy_id="strat_001",
            user_id="user_001",
            name="价值投资策略",
            description="寻找低估值股票",
            status=StrategyStatus.ACTIVE,
            applicable_markets=["A股"],
            screening_criteria={"pe_max": 20, "roe_min": 10},
        )

        assert strategy.strategy_id == "strat_001"
        assert strategy.name == "价值投资策略"
        assert strategy.screening_criteria["pe_max"] == 20

    def test_screening_candidate_model(self):
        """测试选股候选模型"""
        from app.models.personal_investment import ScreeningCandidate

        candidate = ScreeningCandidate(
            stock_code="600519",
            stock_name="贵州茅台",
            match_reasons=["PE低于行业平均", "ROE持续高于15%"],
            risk_warnings=["估值处于历史高位"],
            conflict_with_profile=False,
            score=0.85,
        )

        assert candidate.stock_code == "600519"
        assert len(candidate.match_reasons) == 2
        assert candidate.conflict_with_profile is False

    def test_checkup_result_model(self):
        """测试体检结果模型"""
        from app.models.personal_investment import CheckupResult

        result = CheckupResult(
            result_id="chk_001",
            task_id="task_001",
            fitness_level="medium",
            fitness_summary="当前市场震荡，策略适配度中等",
            data_sufficient=True,
        )

        assert result.fitness_level == "medium"
        assert result.data_sufficient is True


class TestContextBuilder:
    """测试上下文构造器"""

    @pytest.mark.asyncio
    async def test_format_profile_summary(self):
        """测试画像摘要格式化"""
        from app.services.personal_investment.context_builder import ContextBuilder

        summary = {
            "risk_preference": "balanced",
            "trading_style": "value",
            "target_markets": ["A股"],
            "excluded_sectors": ["房地产"],
            "exclude_st": True,
            "max_position_per_stock": 0.2,
            "current_holdings_count": 5,
            "current_holdings": [{
                "stock_code": "000651",
                "stock_name": "格力电器",
                "quantity": 200,
                "cost_price": 38.89,
            }],
        }

        result = ContextBuilder._format_profile_summary(summary)

        assert result is not None
        assert "用户投资画像" in result
        assert "平衡型" in result
        assert "价值投资" in result
        assert "排除 ST 股票" in result
        assert "000651 格力电器" in result
        assert "数量 200 股" in result
        assert "成本价 38.89" in result

    @pytest.mark.asyncio
    async def test_format_strategy_info(self):
        """测试策略信息格式化"""
        from app.services.personal_investment.context_builder import ContextBuilder

        strategy = {
            "name": "红利策略",
            "description": "选择高股息股票",
            "applicable_markets": ["A股"],
            "screening_criteria": {"dividend_yield_min": 3},
            "tags": ["红利", "稳健"],
        }

        result = ContextBuilder._format_strategy_info(strategy)

        assert result is not None
        assert "当前研究策略" in result
        assert "红利策略" in result

    def test_check_profile_conflict_excluded_stock(self):
        """测试禁投标的冲突检查"""
        from app.services.personal_investment.context_builder import ContextBuilder

        profile = {
            "excluded_stocks": ["600519", "000858"],
            "exclude_st": True,
            "excluded_sectors": [],
        }

        conflict = ContextBuilder.check_profile_conflict(
            stock_code="600519",
            stock_info={"name": "贵州茅台"},
            profile=profile,
        )

        assert conflict is not None
        assert "禁投列表" in conflict

    def test_check_profile_conflict_st_stock(self):
        """测试 ST 股票冲突检查"""
        from app.services.personal_investment.context_builder import ContextBuilder

        profile = {
            "excluded_stocks": [],
            "exclude_st": True,
            "excluded_sectors": [],
        }

        conflict = ContextBuilder.check_profile_conflict(
            stock_code="000001",
            stock_info={"name": "*ST 测试"},
            profile=profile,
        )

        assert conflict is not None
        assert "ST" in conflict

    def test_check_profile_conflict_no_conflict(self):
        """测试无冲突情况"""
        from app.services.personal_investment.context_builder import ContextBuilder

        profile = {
            "excluded_stocks": [],
            "exclude_st": True,
            "excluded_sectors": ["房地产"],
        }

        conflict = ContextBuilder.check_profile_conflict(
            stock_code="600519",
            stock_info={"name": "贵州茅台", "sector": "白酒"},
            profile=profile,
        )

        assert conflict is None


class TestRouterProtection:
    """测试路由保护"""

    def test_personal_investment_router_exists(self):
        """验证个人投资助手路由存在"""
        from app.routers import personal_investment

        assert hasattr(personal_investment, "router")
        assert len(personal_investment.router.routes) > 0

    def test_routes_require_auth(self):
        """验证路由需要认证"""
        from app.routers import personal_investment

        # 所有路由都应该有依赖注入（认证）
        for route in personal_investment.router.routes:
            if hasattr(route, "dependant"):
                # 检查是否有 get_current_user 依赖
                deps = route.dependant.dependencies
                assert len(deps) > 0, f"Route {route.path} should require authentication"


class TestUserIsolation:
    """测试用户隔离"""

    def test_profile_service_user_isolation(self):
        """验证画像服务支持用户隔离"""
        from app.services.personal_investment.profile_service import ProfileService

        service = ProfileService()
        assert hasattr(service, "get_profile")
        assert hasattr(service, "create_or_update_profile")

    def test_strategy_service_user_isolation(self):
        """验证策略服务支持用户隔离"""
        from app.services.personal_investment.strategy_service import StrategyService

        service = StrategyService()
        assert hasattr(service, "list_strategies")
        # list_strategies 方法应该接受 user_id 参数
        import inspect
        sig = inspect.signature(service.list_strategies)
        assert "user_id" in sig.parameters


class TestTerminologyFilter:
    """测试术语过滤器"""

    def test_filter_prohibited_buy_sell_terms(self):
        """测试过滤买卖类词汇"""
        from app.services.personal_investment.terminology_filter import TerminologyFilter

        text = "建议买入该股票，预计会有大幅上涨"
        filtered, replacements = TerminologyFilter.filter_text(text)

        assert "买入" not in filtered
        assert "关注" in filtered
        assert len(replacements) > 0

    def test_filter_recommendation_terms(self):
        """测试过滤推荐类词汇"""
        from app.services.personal_investment.terminology_filter import TerminologyFilter

        text = "强烈推荐这只牛股，目标价100元"
        filtered, replacements = TerminologyFilter.filter_text(text)

        assert "强烈推荐" not in filtered
        assert "牛股" not in filtered
        assert "目标价" not in filtered
        assert len(replacements) >= 3

    def test_filter_guarantee_terms(self):
        """测试过滤保证收益类词汇"""
        from app.services.personal_investment.terminology_filter import TerminologyFilter

        text = "这是一只稳赚不赔的股票，无风险投资"
        filtered, replacements = TerminologyFilter.filter_text(text)

        assert "稳赚" not in filtered
        assert "无风险" not in filtered
        assert len(replacements) >= 2

    def test_validate_compliance_clean(self):
        """测试合规验证-合规文本"""
        from app.services.personal_investment.terminology_filter import TerminologyFilter

        text = "该标的近期表现活跃，值得研究和关注"
        result = TerminologyFilter.validate_compliance(text)

        assert result["compliant"] is True
        assert len(result["violations"]) == 0

    def test_validate_compliance_violation(self):
        """测试合规验证-违规文本"""
        from app.services.personal_investment.terminology_filter import TerminologyFilter

        text = "赶紧买入，马上要涨停了"
        result = TerminologyFilter.validate_compliance(text)

        assert result["compliant"] is False
        assert len(result["violations"]) > 0

    def test_filter_screening_result(self):
        """测试过滤选股结果"""
        from app.services.personal_investment.terminology_filter import TerminologyFilter

        result = {
            "candidates": [
                {
                    "stock_code": "600519",
                    "match_reasons": ["强烈推荐理由"],
                    "risk_warnings": ["注意追涨风险"],
                }
            ],
            "overall_risks": ["不要错过最后机会"],
        }

        filtered = TerminologyFilter.filter_screening_result(result)

        assert filtered["terminology_compliant"] is True
        assert "强烈推荐" not in str(filtered["candidates"][0]["match_reasons"])
        assert "追涨" not in str(filtered["candidates"][0]["risk_warnings"])


class TestExecutors:
    """测试执行器"""

    def test_screening_executor_exists(self):
        """验证筛选执行器存在"""
        from app.services.personal_investment.screening_executor import screening_executor

        assert hasattr(screening_executor, "execute")

    def test_checkup_executor_exists(self):
        """验证体检执行器存在"""
        from app.services.personal_investment.checkup_executor import checkup_executor

        assert hasattr(checkup_executor, "execute")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
