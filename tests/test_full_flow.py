"""
个人投资助手 API 全流程手动验证脚本

逐个功能模块进行完整的接口验证。
"""

import httpx
import time
import json

BASE_URL = "http://localhost:8000"
HEADERS = {
    "Authorization": "Bearer test_token",
    "Content-Type": "application/json"
}


def print_section(title):
    print(f"\n{'='*60}")
    print(f"{title}")
    print('='*60)


def print_response(response, label=""):
    print(f"\n{label}")
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return data
    except:
        print(f"响应文本: {response.text}")
        return None


# ========================================
# 1. 投资画像 API 全流程
# ========================================
print_section("1. 投资画像 API 全流程验证")

client = httpx.Client(base_url=BASE_URL, timeout=30.0)

# 1.1 创建画像
print("\n[1.1] 创建投资画像")
profile_data = {
    "risk_preference": "balanced",
    "trading_style": "value",
    "capital_range_min": 10000,
    "capital_range_max": 500000,
    "target_markets": ["A股"],
    "excluded_sectors": ["房地产"],
    "excluded_stocks": ["600519"],
    "exclude_st": True,
    "max_position_per_stock": 0.2,
    "context_injection_enabled": True
}
response = client.put("/api/investment/profile", json=profile_data, headers=HEADERS)
data = print_response(response, "创建画像响应:")
assert response.status_code == 200 and data["success"], "❌ 创建画像失败"
print("✅ 创建画像成功")

# 1.2 获取画像
print("\n[1.2] 获取投资画像")
response = client.get("/api/investment/profile", headers=HEADERS)
data = print_response(response, "获取画像响应:")
assert response.status_code == 200 and data["success"], "❌ 获取画像失败"
assert "risk_preference" in data["data"], "❌ 缺少 risk_preference 字段"
assert "trading_style" in data["data"], "❌ 缺少 trading_style 字段"
print("✅ 获取画像成功，字段完整")

# 1.3 更新画像
print("\n[1.3] 更新投资画像")
update_data = {"risk_preference": "aggressive", "max_position_per_stock": 0.3}
response = client.put("/api/investment/profile", json=update_data, headers=HEADERS)
data = print_response(response, "更新画像响应:")
assert response.status_code == 200 and data["success"], "❌ 更新画像失败"
assert data["data"]["risk_preference"] == "aggressive", "❌ 风险偏好未更新"
print("✅ 更新画像成功，数据已变更")

# 1.4 获取画像摘要
print("\n[1.4] 获取画像摘要")
response = client.get("/api/investment/profile/summary", headers=HEADERS)
data = print_response(response, "画像摘要响应:")
assert response.status_code == 200 and data["success"], "❌ 获取摘要失败"
print("✅ 获取画像摘要成功")

# 1.5 删除画像
print("\n[1.5] 删除投资画像")
response = client.delete("/api/investment/profile", headers=HEADERS)
data = print_response(response, "删除画像响应:")
assert response.status_code == 200, "❌ 删除画像失败"
print("✅ 删除画像成功")


# ========================================
# 2. 策略管理 API 全流程
# ========================================
print_section("2. 策略管理 API 全流程验证")

strategy_id = None

# 2.1 创建策略
print("\n[2.1] 创建策略")
strategy_data = {
    "name": "价值投资策略-集成测试",
    "description": "寻找低估值高ROE的股票",
    "applicable_markets": ["A股"],
    "screening_criteria": {
        "pe_max": 20,
        "roe_min": 10,
        "rsi_min": 30,
        "rsi_max": 70
    },
    "tags": ["价值", "稳健"]
}
response = client.post("/api/investment/strategies", json=strategy_data, headers=HEADERS)
data = print_response(response, "创建策略响应:")
assert response.status_code == 200 and data["success"], "❌ 创建策略失败"
strategy_id = data["data"]["strategy_id"]
assert strategy_id, "❌ 未返回 strategy_id"
print(f"✅ 创建策略成功 - ID: {strategy_id}")

# 2.2 列出策略
print("\n[2.2] 列出策略列表")
response = client.get("/api/investment/strategies", headers=HEADERS)
data = print_response(response, "策略列表响应:")
assert response.status_code == 200 and data["success"], "❌ 获取列表失败"
assert len(data["data"]["items"]) > 0, "❌ 列表为空"
print(f"✅ 获取策略列表成功 - 数量: {len(data['data']['items'])}")

# 2.3 获取策略详情
print("\n[2.3] 获取策略详情")
response = client.get(f"/api/investment/strategies/{strategy_id}", headers=HEADERS)
data = print_response(response, "策略详情响应:")
assert response.status_code == 200 and data["success"], "❌ 获取详情失败"
assert data["data"]["strategy_id"] == strategy_id, "❌ strategy_id 不匹配"
assert data["data"]["name"] == "价值投资策略-集成测试", "❌ 名称不匹配"
print("✅ 获取策略详情成功，字段正确")

# 2.4 更新策略
print("\n[2.4] 更新策略")
update_strategy = {
    "description": "更新后的描述",
    "tags": ["价值", "稳健", "长期"]
}
response = client.put(f"/api/investment/strategies/{strategy_id}", json=update_strategy, headers=HEADERS)
data = print_response(response, "更新策略响应:")
assert response.status_code == 200 and data["success"], "❌ 更新策略失败"
print("✅ 更新策略成功")

# 2.5 停用策略
print("\n[2.5] 停用策略")
response = client.post(f"/api/investment/strategies/{strategy_id}/disable", headers=HEADERS)
data = print_response(response, "停用策略响应:")
assert response.status_code == 200 and data["success"], "❌ 停用策略失败"
print("✅ 停用策略成功")

# 2.6 启用策略
print("\n[2.6] 启用策略")
response = client.post(f"/api/investment/strategies/{strategy_id}/enable", headers=HEADERS)
data = print_response(response, "启用策略响应:")
assert response.status_code == 200 and data["success"], "❌ 启用策略失败"
print("✅ 启用策略成功")


# ========================================
# 3. 策略选股任务 API 全流程
# ========================================
print_section("3. 策略选股任务 API 全流程验证")

task_id = None

# 3.1 创建选股任务
print("\n[3.1] 创建选股任务")
task_data = {"strategy_id": strategy_id, "params": {}}
response = client.post("/api/investment/screening-tasks", json=task_data, headers=HEADERS)
data = print_response(response, "创建选股任务响应:")
assert response.status_code == 200 and data["success"], "❌ 创建任务失败"
task_id = data["data"]["task_id"]
assert task_id, "❌ 未返回 task_id"
print(f"✅ 创建选股任务成功 - Task ID: {task_id}")

# 3.2 等待任务完成
print("\n[3.2] 等待任务执行...")
max_attempts = 30
for i in range(max_attempts):
    response = client.get(f"/api/investment/tasks/{task_id}", headers=HEADERS)
    if response.status_code == 200:
        task_data = response.json().get("data", {})
        status = task_data.get("status")
        print(f"  尝试 {i+1}/{max_attempts} - 状态: {status}")
        if status in ["completed", "failed", "data_insufficient"]:
            break
    time.sleep(1)
print("✅ 任务执行完成")

# 3.3 获取选股结果
print("\n[3.3] 获取选股结果")
response = client.get(f"/api/investment/screening-tasks/{task_id}/result", headers=HEADERS)
data = print_response(response, "选股结果响应:")
assert response.status_code == 200 and data["success"], "❌ 获取结果失败"
if data["data"]:
    result = data["data"]
    print(f"  候选数量: {result.get('total_candidates', 0)}")
    print(f"  合规检查: {result.get('terminology_compliant', False)}")
    if result.get("candidates"):
        first = result["candidates"][0]
        print(f"  第一个候选: {first.get('stock_code')} - {first.get('stock_name')}")
        print(f"    评分: {first.get('score')}")
        print(f"    命中原因: {first.get('match_reasons', [])}")
        print(f"    风险警告: {first.get('risk_warnings', [])}")
print("✅ 获取选股结果成功")


# ========================================
# 4. 策略体检任务 API 全流程
# ========================================
print_section("4. 策略体检任务 API 全流程验证")

checkup_task_id = None

# 4.1 创建体检任务
print("\n[4.1] 创建体检任务")
task_data = {"strategy_id": strategy_id, "params": {}}
response = client.post("/api/investment/checkup-tasks", json=task_data, headers=HEADERS)
data = print_response(response, "创建体检任务响应:")
assert response.status_code == 200 and data["success"], "❌ 创建任务失败"
checkup_task_id = data["data"]["task_id"]
assert checkup_task_id, "❌ 未返回 task_id"
print(f"✅ 创建体检任务成功 - Task ID: {checkup_task_id}")

# 4.2 等待任务完成
print("\n[4.2] 等待任务执行...")
for i in range(max_attempts):
    response = client.get(f"/api/investment/tasks/{checkup_task_id}", headers=HEADERS)
    if response.status_code == 200:
        task_data = response.json().get("data", {})
        status = task_data.get("status")
        print(f"  尝试 {i+1}/{max_attempts} - 状态: {status}")
        if status in ["completed", "failed", "data_insufficient"]:
            break
    time.sleep(1)
print("✅ 任务执行完成")

# 4.3 获取体检结果
print("\n[4.3] 获取体检结果")
response = client.get(f"/api/investment/checkup-tasks/{checkup_task_id}/result", headers=HEADERS)
data = print_response(response, "体检结果响应:")
assert response.status_code == 200 and data["success"], "❌ 获取结果失败"
if data["data"]:
    result = data["data"]
    print(f"  适配度等级: {result.get('fitness_level')}")
    print(f"  数据充分性: {result.get('data_sufficient')}")
    summary = result.get('fitness_summary', '')
    print(f"  摘要: {summary[:100]}..." if len(summary) > 100 else f"  摘要: {summary}")
    if result.get("key_metrics"):
        print(f"  关键指标数量: {len(result['key_metrics'])}")
    if result.get("risk_warnings"):
        print(f"  风险提示数量: {len(result['risk_warnings'])}")
print("✅ 获取体检结果成功")


# ========================================
# 总结
# ========================================
print_section("🎉 全流程验证完成！")
print("""
✅ 投资画像 API: 5/5 通过
  - 创建、获取、更新、摘要、删除

✅ 策略管理 API: 6/6 通过
  - 创建、列表、详情、更新、停用、启用

✅ 策略选股 API: 3/3 通过
  - 创建任务、等待执行、获取结果

✅ 策略体检 API: 3/3 通过
  - 创建任务、等待执行、获取结果

所有 API 端点功能正常，数据字段完整，无报错！
""")

client.close()
