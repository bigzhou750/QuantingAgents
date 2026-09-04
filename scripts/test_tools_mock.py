#!/usr/bin/env python3
"""
Vibe Agent Runtime 工具链 Mock 测试
直接调用工具的 execute() 方法，绕过 grounding/identity 机制，
验证每个工具在容器环境中是否能正常工作。

用法（在服务器上）:
  docker exec -it $(docker ps -qf name=backend) python scripts/test_tools_mock.py
或在本地:
  cd /opt/tradingagents/worktree && python scripts/test_tools_mock.py
"""

import json
import sys
import time
import traceback
from pathlib import Path

# 添加 vendor 路径
vendor_root = Path(__file__).resolve().parent.parent / "vibe_agent_runtime" / "vendor"
if vendor_root.is_dir() and str(vendor_root) not in sys.path:
    sys.path.insert(0, str(vendor_root))


def test_symbol_search():
    """测试标的搜索工具"""
    from src.tools.symbol_search_tool import SymbolSearchTool
    tool = SymbolSearchTool()
    result = tool.execute(query="贵州茅台", limit=3)
    data = json.loads(result)
    print(f"  ok={data.get('ok')}, source={data.get('source')}")
    if data.get("ok") and data.get("data"):
        items = data["data"].get("items", [])
        for item in items[:3]:
            print(f"    → {item.get('symbol', '?')} {item.get('name', '?')} ({item.get('market', '?')})")
    return data.get("ok", False)


def test_market_data():
    """测试市场数据工具（K线）"""
    from src.tools.market_data_tool import MarketDataTool
    tool = MarketDataTool()
    result = tool.execute(
        codes=["600519.SH"],
        start_date="2026-09-01",
        end_date="2026-09-04",
        source="eastmoney",
        interval="1D",
    )
    data = json.loads(result)
    status = data.get("status")
    print(f"  status={status}")
    if status == "ok" and data.get("data"):
        panels = data["data"].get("panels", {})
        for code, panel in list(panels.items())[:1]:
            rows = panel.get("rows", [])
            print(f"    → {code}: {len(rows)} bars")
            if rows:
                print(f"      last: {rows[-1]}")
    elif status == "error":
        print(f"    error: {data.get('error', 'unknown')}")
    return status == "ok"


def test_fund_flow():
    """测试资金流向工具"""
    try:
        from src.tools.fund_flow_tool import FundFlowTool
        tool = FundFlowTool()
        result = tool.execute(codes=["600519.SH"])
        data = json.loads(result)
        status = data.get("status", data.get("ok"))
        print(f"  status={status}")
        if data.get("error"):
            print(f"    error: {data['error'][:100]}")
        return bool(status and status != "error")
    except Exception as e:
        print(f"  exception: {e}")
        return False


def test_stock_news():
    """测试股票新闻工具"""
    try:
        from src.tools.stock_news_tool import StockNewsTool
        tool = StockNewsTool()
        result = tool.execute(symbol="600519.SH", limit=3)
        data = json.loads(result)
        status = data.get("status", data.get("ok"))
        print(f"  status={status}")
        if data.get("error"):
            print(f"    error: {str(data['error'])[:100]}")
        if data.get("data") and isinstance(data["data"], dict):
            news = data["data"].get("news", data["data"].get("items", []))
            print(f"    → {len(news)} news items")
        return bool(status and status != "error")
    except Exception as e:
        print(f"  exception: {e}")
        return False


def test_northbound():
    """测试北向资金工具"""
    try:
        from src.tools.northbound_tool import NorthboundTool
        tool = NorthboundTool()
        result = tool.execute()
        data = json.loads(result)
        status = data.get("status", data.get("ok"))
        print(f"  status={status}")
        if data.get("error"):
            print(f"    error: {str(data['error'])[:100]}")
        return bool(status and status != "error")
    except Exception as e:
        print(f"  exception: {e}")
        return False


def test_web_search():
    """测试 Web 搜索工具"""
    try:
        from src.tools.web_search_tool import WebSearchTool
        tool = WebSearchTool()
        result = tool.execute(query="A股 今日 大盘", max_results=3)
        data = json.loads(result)
        status = data.get("status", data.get("ok"))
        print(f"  status={status}")
        if data.get("error"):
            print(f"    error: {str(data['error'])[:100]}")
        if data.get("results"):
            print(f"    → {len(data['results'])} results")
        return bool(status and status != "error")
    except ImportError:
        # 可能叫别的名字
        print("  ⚠️  WebSearchTool not found, trying alternatives...")
        return None
    except Exception as e:
        print(f"  exception: {e}")
        return False


def test_registry():
    """测试工具注册表完整性"""
    try:
        from src.tools import build_tool_registry
        registry = build_tool_registry()
        names = registry.tool_names
        print(f"  已注册工具数: {len(names)}")
        import_failures = registry.import_failures
        reg_failures = registry.registration_failures
        if import_failures:
            print(f"  ⚠️  导入失败 ({len(import_failures)}):")
            for mod, reason in import_failures.items():
                print(f"    → {mod}: {reason[:80]}")
        if reg_failures:
            print(f"  ⚠️  注册失败 ({len(reg_failures)}):")
            for name, reason in reg_failures.items():
                print(f"    → {name}: {reason[:80]}")
        print(f"  可用工具列表:")
        for name in sorted(names):
            print(f"    ✓ {name}")
        return len(names), len(import_failures) + len(reg_failures)
    except Exception as e:
        print(f"  exception: {e}")
        traceback.print_exc()
        return 0, 0


def main():
    print("=" * 60)
    print("Vibe Agent Runtime 工具链 Mock 测试")
    print("=" * 60)

    # 1. 工具注册表
    print("\n📋 [1/7] 工具注册表完整性")
    total, failures = test_registry()

    # 2. 标的搜索
    print("\n🔍 [2/7] symbol_search (贵州茅台)")
    t0 = time.time()
    ok = test_symbol_search()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 3. K线数据
    print("\n📈 [3/7] get_market_data (600519.SH)")
    t0 = time.time()
    ok = test_market_data()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 4. 资金流向
    print("\n💰 [4/7] fund_flow (600519.SH)")
    t0 = time.time()
    ok = test_fund_flow()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 5. 股票新闻
    print("\n📰 [5/7] stock_news (600519.SH)")
    t0 = time.time()
    ok = test_stock_news()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 6. 北向资金
    print("\n🔄 [6/7] northbound")
    t0 = time.time()
    ok = test_northbound()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 7. Web 搜索
    print("\n🌐 [7/7] web_search")
    t0 = time.time()
    ok = test_web_search()
    elapsed = time.time() - t0
    if ok is None:
        print(f"  耗时: {elapsed:.1f}s, 结果: ⚠️ 跳过")
    else:
        print(f"  耗时: {elapsed:.1f}s, 结果: {'✅' if ok else '❌'}")

    print("\n" + "=" * 60)
    print(f"注册工具: {total}, 失败: {failures}")
    print("=" * 60)


if __name__ == "__main__":
    main()
