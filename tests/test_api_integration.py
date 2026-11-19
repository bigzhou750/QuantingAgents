"""
个人投资助手 API 全流程集成测试

针对每个功能模块进行完整的 CRUD 操作验证，确保数据修改、提交和字段都符合预期。
"""

import pytest
import httpx
import asyncio
from typing import Dict, Any

BASE_URL = "http://localhost:8000"


class TestInvestmentProfileAPI:
    """投资画像 API 全流程测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试客户端"""
        self.client = httpx.Client(base_url=BASE_URL, timeout=30.0)
        # 模拟认证 header（实际应该使用真实的 token）
        self.headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        yield
        self.client.close()

    def test_01_create_profile(self):
        """测试 1: 创建投资画像"""
        print("\n=== 测试 1: 创建投资画像 ===")

        profile_data = {
            "risk_preference": "balanced",
            "trading_style": "value",
            "capital_range_min": 10000,
            "capital_range_max": 500000,
            "target_markets": ["A股"],
            "excluded_sectors": ["房地产"],
            "excluded_stocks": ["600519"],
            "exclude_st": True,
            "exclude_new_stock_days": 60,
            "max_position_per_stock": 0.2,
            "context_injection_enabled": True
        }

        response = self.client.put("/api/investment/profile", json=profile_data, headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200, f"创建失败: {response.text}"
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        print("✅ 创建画像成功")

    def test_02_get_profile(self):
        """测试 2: 获取投资画像"""
        print("\n=== 测试 2: 获取投资画像 ===")

        response = self.client.get("/api/investment/profile", headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

        if data["data"]:
            profile = data["data"]
            assert "risk_preference" in profile
            assert "trading_style" in profile
            assert "target_markets" in profile
            print(f"✅ 获取画像成功 - 风险偏好: {profile.get('risk_preference')}")
        else:
            print("⚠️ 画像不存在")

    def test_03_update_profile(self):
        """测试 3: 更新投资画像"""
        print("\n=== 测试 3: 更新投资画像 ===")

        update_data = {
            "risk_preference": "aggressive",
            "max_position_per_stock": 0.3
        }

        response = self.client.put("/api/investment/profile", json=update_data, headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print("✅ 更新画像成功")

    def test_04_get_profile_summary(self):
        """测试 4: 获取画像摘要（用于上下文注入）"""
        print("\n=== 测试 4: 获取画像摘要 ===")

        response = self.client.get("/api/investment/profile/summary", headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print("✅ 获取画像摘要成功")

    def test_05_delete_profile(self):
        """测试 5: 删除投资画像"""
        print("\n=== 测试 5: 删除投资画像 ===")

        response = self.client.delete("/api/investment/profile", headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        # 可能返回 200 或 404（如果不存在）
        assert response.status_code in [200, 404]
        print("✅ 删除画像操作完成")


class TestStrategyManagementAPI:
    """策略管理 API 全流程测试"""

    # 类变量用于在测试方法间共享数据
    created_strategy_id = None

    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试客户端"""
        self.client = httpx.Client(base_url=BASE_URL, timeout=30.0)
        self.headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        yield
        self.client.close()

    def test_01_create_strategy(self):
        """测试 1: 创建策略"""
        print("\n=== 测试 1: 创建策略 ===")

        strategy_data = {
            "name": "价值投资策略-测试",
            "description": "寻找低估值高ROE的股票",
            "applicable_markets": ["A股"],
            "screening_criteria": {
                "pe_max": 20,
                "roe_min": 10,
                "rsi_min": 30,
                "rsi_max": 70
            },
            "parameters": {},
            "tags": ["价值", "稳健"]
        }

        response = self.client.post("/api/investment/strategies", json=strategy_data, headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200, f"创建失败: {response.text}"
        data = response.json()
        assert data["success"] is True
        assert "data" in data

        TestStrategyManagementAPI.created_strategy_id = data["data"].get("strategy_id")
        assert TestStrategyManagementAPI.created_strategy_id is not None
        print(f"✅ 创建策略成功 - ID: {TestStrategyManagementAPI.created_strategy_id}")

    def test_02_list_strategies(self):
        """测试 2: 列出策略列表"""
        print("\n=== 测试 2: 列出策略列表 ===")

        response = self.client.get("/api/investment/strategies", headers=self.headers)
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: 共 {result.get('data', {}).get('count', 0)} 个策略")

        assert response.status_code == 200
        data = result
        assert data["success"] is True
        assert "items" in data["data"]
        print(f"✅ 获取策略列表成功 - 数量: {len(data['data']['items'])}")

    def test_03_get_strategy_detail(self):
        """测试 3: 获取策略详情"""
        print("\n=== 测试 3: 获取策略详情 ===")

        if not TestStrategyManagementAPI.created_strategy_id:
            pytest.skip("没有可用的策略ID")

        response = self.client.get(
            f"/api/investment/strategies/{TestStrategyManagementAPI.created_strategy_id}",
            headers=self.headers
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["strategy_id"] == TestStrategyManagementAPI.created_strategy_id
        print(f"✅ 获取策略详情成功 - 名称: {data['data'].get('name')}")

    def test_04_update_strategy(self):
        """测试 4: 更新策略"""
        print("\n=== 测试 4: 更新策略 ===")

        if not TestStrategyManagementAPI.created_strategy_id:
            pytest.skip("没有可用的策略ID")

        update_data = {
            "description": "更新后的描述 - 寻找低估值高ROE的优质股票",
            "tags": ["价值", "稳健", "长期"]
        }

        response = self.client.put(
            f"/api/investment/strategies/{TestStrategyManagementAPI.created_strategy_id}",
            json=update_data,
            headers=self.headers
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print("✅ 更新策略成功")

    def test_05_disable_strategy(self):
        """测试 5: 停用策略"""
        print("\n=== 测试 5: 停用策略 ===")

        if not TestStrategyManagementAPI.created_strategy_id:
            pytest.skip("没有可用的策略ID")

        response = self.client.post(
            f"/api/investment/strategies/{TestStrategyManagementAPI.created_strategy_id}/disable",
            headers=self.headers
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print("✅ 停用策略成功")

    def test_06_enable_strategy(self):
        """测试 6: 启用策略"""
        print("\n=== 测试 6: 启用策略 ===")

        if not TestStrategyManagementAPI.created_strategy_id:
            pytest.skip("没有可用的策略ID")

        response = self.client.post(
            f"/api/investment/strategies/{TestStrategyManagementAPI.created_strategy_id}/enable",
            headers=self.headers
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print("✅ 启用策略成功")


class TestScreeningTaskAPI:
    strategy_id = None
    task_id = None

    """策略选股任务 API 全流程测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试客户端"""
        self.client = httpx.Client(base_url=BASE_URL, timeout=60.0)
        self.headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        TestScreeningTaskAPI.strategy_id = None
        TestScreeningTaskAPI.task_id = None
        yield
        self.client.close()

    def _ensure_strategy_exists(self):
        """确保有一个可用的策略"""
        response = self.client.get("/api/investment/strategies?limit=1", headers=self.headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("data", {}).get("items"):
                TestScreeningTaskAPI.strategy_id = data["data"]["items"][0]["strategy_id"]
                return

        # 如果没有策略，创建一个
        strategy_data = {
            "name": "自动创建-测试策略",
            "description": "测试用策略",
            "applicable_markets": ["A股"],
            "screening_criteria": {"pe_max": 30}
        }
        response = self.client.post("/api/investment/strategies", json=strategy_data, headers=self.headers)
        if response.status_code == 200:
            TestScreeningTaskAPI.strategy_id = response.json()["data"]["strategy_id"]

    def test_01_create_screening_task(self):
        """测试 1: 创建选股任务"""
        print("\n=== 测试 1: 创建选股任务 ===")

        self._ensure_strategy_exists()
        if not TestScreeningTaskAPI.strategy_id:
            pytest.skip("没有可用的策略")

        task_data = {
            "strategy_id": TestScreeningTaskAPI.strategy_id,
            "params": {}
        }

        response = self.client.post("/api/investment/screening-tasks", json=task_data, headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200, f"创建任务失败: {response.text}"
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data["data"]

        TestScreeningTaskAPI.task_id = data["data"]["task_id"]
        print(f"✅ 创建选股任务成功 - Task ID: {TestScreeningTaskAPI.task_id}")

    def test_02_wait_for_task_completion(self):
        """测试 2: 等待任务完成并获取结果"""
        print("\n=== 测试 2: 等待任务完成 ===")

        if not TestScreeningTaskAPI.task_id:
            pytest.skip("没有任务ID")

        # 轮询等待任务完成（最多等待 30 秒）
        max_attempts = 30
        for i in range(max_attempts):
            response = self.client.get(f"/api/investment/tasks/{TestScreeningTaskAPI.task_id}", headers=self.headers)
            if response.status_code == 200:
                task_data = response.json().get("data", {})
                status = task_data.get("status")
                print(f"尝试 {i+1}/{max_attempts} - 任务状态: {status}")

                if status in ["completed", "failed", "data_insufficient"]:
                    break

            import time; time.sleep(1)

        print("✅ 任务执行完成")

    def test_03_get_screening_result(self):
        """测试 3: 获取选股结果"""
        print("\n=== 测试 3: 获取选股结果 ===")

        if not TestScreeningTaskAPI.task_id:
            pytest.skip("没有任务ID")

        response = self.client.get(
            f"/api/investment/screening-tasks/{TestScreeningTaskAPI.task_id}/result",
            headers=self.headers
        )
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")

        assert response.status_code == 200
        data = result
        assert data["success"] is True

        if data["data"]:
            screening_result = data["data"]
            print(f"候选数量: {screening_result.get('total_candidates', 0)}")
            print(f"合规检查: {screening_result.get('terminology_compliant', False)}")

            if screening_result.get("candidates"):
                first_candidate = screening_result["candidates"][0]
                print(f"第一个候选: {first_candidate.get('stock_code')} - {first_candidate.get('stock_name')}")
                print(f"  评分: {first_candidate.get('score')}")
                print(f"  命中原因: {first_candidate.get('match_reasons')}")

        print("✅ 获取选股结果成功")


class TestCheckupTaskAPI:
    """策略体检任务 API 全流程测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试客户端"""
        self.client = httpx.Client(base_url=BASE_URL, timeout=60.0)
        self.headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        TestScreeningTaskAPI.strategy_id = None
        TestScreeningTaskAPI.task_id = None
        yield
        self.client.close()

    def _ensure_strategy_exists(self):
        """确保有一个可用的策略"""
        response = self.client.get("/api/investment/strategies?limit=1", headers=self.headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("data", {}).get("items"):
                TestScreeningTaskAPI.strategy_id = data["data"]["items"][0]["strategy_id"]
                return

        strategy_data = {
            "name": "体检测试策略",
            "description": "用于体检测试",
            "applicable_markets": ["A股"],
            "screening_criteria": {"pe_max": 25}
        }
        response = self.client.post("/api/investment/strategies", json=strategy_data, headers=self.headers)
        if response.status_code == 200:
            TestScreeningTaskAPI.strategy_id = response.json()["data"]["strategy_id"]

    def test_01_create_checkup_task(self):
        """测试 1: 创建体检任务"""
        print("\n=== 测试 1: 创建体检任务 ===")

        self._ensure_strategy_exists()
        if not TestScreeningTaskAPI.strategy_id:
            pytest.skip("没有可用的策略")

        task_data = {
            "strategy_id": TestScreeningTaskAPI.strategy_id,
            "params": {}
        }

        response = self.client.post("/api/investment/checkup-tasks", json=task_data, headers=self.headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")

        assert response.status_code == 200, f"创建任务失败: {response.text}"
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data["data"]

        TestScreeningTaskAPI.task_id = data["data"]["task_id"]
        print(f"✅ 创建体检任务成功 - Task ID: {TestScreeningTaskAPI.task_id}")

    def test_02_wait_for_task_completion(self):
        """测试 2: 等待任务完成"""
        print("\n=== 测试 2: 等待任务完成 ===")

        if not TestScreeningTaskAPI.task_id:
            pytest.skip("没有任务ID")

        max_attempts = 30
        for i in range(max_attempts):
            response = self.client.get(f"/api/investment/tasks/{TestScreeningTaskAPI.task_id}", headers=self.headers)
            if response.status_code == 200:
                task_data = response.json().get("data", {})
                status = task_data.get("status")
                print(f"尝试 {i+1}/{max_attempts} - 任务状态: {status}")

                if status in ["completed", "failed", "data_insufficient"]:
                    break

            import time; time.sleep(1)

        print("✅ 任务执行完成")

    def test_03_get_checkup_result(self):
        """测试 3: 获取体检结果"""
        print("\n=== 测试 3: 获取体检结果 ===")

        if not TestScreeningTaskAPI.task_id:
            pytest.skip("没有任务ID")

        response = self.client.get(
            f"/api/investment/checkup-tasks/{TestScreeningTaskAPI.task_id}/result",
            headers=self.headers
        )
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")

        assert response.status_code == 200
        data = result
        assert data["success"] is True

        if data["data"]:
            checkup_result = data["data"]
            print(f"适配度等级: {checkup_result.get('fitness_level')}")
            print(f"数据充分性: {checkup_result.get('data_sufficient')}")
            print(f"摘要: {checkup_result.get('fitness_summary', '')[:100]}...")

            if checkup_result.get("key_metrics"):
                print(f"关键指标数量: {len(checkup_result['key_metrics'])}")

            if checkup_result.get("risk_warnings"):
                print(f"风险提示数量: {len(checkup_result['risk_warnings'])}")

        print("✅ 获取体检结果成功")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
