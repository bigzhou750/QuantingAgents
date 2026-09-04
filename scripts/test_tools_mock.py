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


def test_registry():
    """测试工具注册表完整性"""
    try:
        from src.tools import build_registry
        registry = build_registry()
        names = registry.tool_names
        print(f"  已注册工具数: {len(names)}")
        import_failures = registry.import_failures
        reg_failures = registry.registration_failures
        if import_failures:
            print(f"  ⚠️  导入失败 ({len(import_failures)}):")
            for mod, reason in import_failures.items():
                print(f"    → {mod}: {reason[:120]}")
        if reg_failures:
            print(f"  ⚠️  注册失败 ({len(reg_failures)}):")
            for name, reason in reg_failures.items():
                print(f"    → {name}: {reason[:120]}")
        print(f"  可用工具:")
        for name in sorted(names):
            print(f"    ✓ {name}")
        return len(names), len(import_failures) + len(reg_failures)
    except Exception as e:
        print(f"  exception: {e}")
        traceback.print_exc()
        return 0, 0


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


def test_market_data_multi_source():
    """测试市场数据工具 - 多数据源对比"""
    from src.tools.market_data_tool import MarketDataTool
    tool = MarketDataTool()
    sources = ["eastmoney", "baostock", "akshare", "tencent", "auto"]
    results = {}
    for src in sources:
        t0 = time.time()
        try:
            result = tool.execute(
                codes=["600519.SH"],
                start_date="2026-09-01",
                end_date="2026-09-04",
                source=src,
                interval="1D",
            )
            elapsed = time.time() - t0
            data = json.loads(result)
            status = data.get("status")
            bars = 0
            if status == "ok" and data.get("data"):
                panels = data["data"].get("panels", {})
                for code, panel in panels.items():
                    bars = len(panel.get("rows", []))
            error = data.get("error", "")
            results[src] = {"status": status, "bars": bars, "time": elapsed, "error": error}
            icon = "✅" if status == "ok" and bars > 0 else "❌"
            print(f"  {icon} {src:12s} status={status}, bars={bars}, {elapsed:.1f}s")
            if error:
                print(f"      error: {str(error)[:120]}")
        except Exception as e:
            elapsed = time.time() - t0
            results[src] = {"status": "exception", "bars": 0, "time": elapsed, "error": str(e)}
            print(f"  ❌ {src:12s} EXCEPTION {elapsed:.1f}s: {str(e)[:120]}")
    return results


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
            print(f"    error: {str(data['error'])[:120]}")
        return bool(status and status != "error")
    except Exception as e:
        print(f"  exception: {e}")
        return False


def test_stock_news():
    """测试股票新闻工具"""
    try:
        from src.tools.stock_news_tool import StockNewsTool
        tool = StockNewsTool()
        # stock_news 需要 code 参数而非 symbol
        result = tool.execute(code="600519", scope="stock", limit=3)
        data = json.loads(result)
        status = data.get("status", data.get("ok"))
        print(f"  status={status}")
        if data.get("error"):
            print(f"    error: {str(data['error'])[:120]}")
        if data.get("data") and isinstance(data["data"], dict):
            news = data["data"].get("news", data["data"].get("items", []))
            print(f"    → {len(news)} news items")
        elif data.get("data") and isinstance(data["data"], list):
            print(f"    → {len(data['data'])} news items")
        return bool(status and status != "error")
    except Exception as e:
        print(f"  exception: {e}")
        traceback.print_exc()
        return False


def test_northbound():
    """测试北向资金工具"""
    try:
        from src.tools.northbound_tool import NorthboundFlowTool
        tool = NorthboundFlowTool()
        result = tool.execute()
        data = json.loads(result)
        status = data.get("status", data.get("ok"))
        print(f"  status={status}")
        if data.get("error"):
            print(f"    error: {str(data['error'])[:120]}")
        return bool(status and status != "error")
    except Exception as e:
        print(f"  exception: {e}")
        traceback.print_exc()
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
            print(f"    error: {str(data['error'])[:120]}")
        if data.get("results"):
            print(f"    → {len(data['results'])} results")
        return bool(status and status != "error")
    except ImportError:
        print("  ⚠️  WebSearchTool not found")
        return None
    except Exception as e:
        print(f"  exception: {e}")
        return False


def main():
    print("=" * 60)
    print("Vibe Agent Runtime 工具链 Mock 测试 v2")
    print("=" * 60)

    # 1. 工具注册表
    print("\n📋 [1/7] 工具注册表完整性")
    total, failures = test_registry()

    # 2. 标的搜索
    print("\n🔍 [2/7] symbol_search (贵州茅台)")
    t0 = time.time()
    ok = test_symbol_search()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 3. K线数据 - 多数据源对比
    print("\n📈 [3/7] get_market_data (600519.SH) - 多源对比")
    md_results = test_market_data_multi_source()
    working_sources = [s for s, r in md_results.items() if r["status"] == "ok" and r["bars"] > 0]
    print(f"  可用数据源: {working_sources or '无!'}")

    # 4. 资金流向
    print("\n💰 [4/7] fund_flow (600519.SH)")
    t0 = time.time()
    ok = test_fund_flow()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 5. 股票新闻
    print("\n📰 [5/7] stock_news (600519)")
    t0 = time.time()
    ok = test_stock_news()
    print(f"  耗时: {time.time()-t0:.1f}s, 结果: {'✅' if ok else '❌'}")

    # 6. 北向资金
    print("\n🔄 [6/7] northbound_flow")
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

    # 8. Tencent 默认数据源验证
    print("\n🔧 [8/8] tencent 默认数据源验证")
    test_tencent_default_source()

    # 汇总
    print("\n" + "=" * 60)
    print(f"注册工具: {total}, 注册失败: {failures}")
    if md_results:
        ok_sources = [s for s, r in md_results.items() if r["status"] == "ok" and r["bars"] > 0]
        fail_sources = [s for s, r in md_results.items() if r["status"] != "ok" or r["bars"] == 0]
        print(f"K线数据源: ✅ {ok_sources}  ❌ {fail_sources}")
    print("=" * 60)


def test_tencent_default_source():
    """验证 tencent 作为 A股默认数据源的可用性。

    系统已将 A股 (.SH/.SZ/.BJ) 的首选数据源设为 tencent，
    因为 eastmoney 对数据中心 IP 段有封锁。此测试验证：
    1. auto 模式下 A股是否正确路由到 tencent
    2. tencent loader 是否能正常返回 K线数据
    """
    import os
    import time

    # 清除代理环境变量，避免干扰
    for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
        os.environ.pop(k, None)

    from src.market_data import detect_source

    # 测试1: auto 检测是否正确路由到 tencent
    print("  --- auto 数据源检测 ---")
    test_symbols = ["600519.SH", "000001.SZ", "00700.HK"]
    for sym in test_symbols:
        detected = detect_source(sym)
        icon = "✅" if detected == "tencent" else "⚠️"
        print(f"  {icon} {sym} -> {detected}")

    # 测试2: tencent loader 直接调用
    print("  --- tencent loader 直接调用 ---")
    from backtest.loaders.tencent_loader import DataLoader

    loader = DataLoader()
    t0 = time.time()
    try:
        result = loader.fetch(["600519.SH"], "2026-09-01", "2026-09-04", interval="1D")
        elapsed = time.time() - t0
        if "600519.SH" in result and not result["600519.SH"].empty:
            df = result["600519.SH"]
            print(f"  ✅ tencent loader 成功, {len(df)} 条K线, {elapsed:.1f}s")
            print(f"     示例: {df.iloc[0].to_dict()}")
            loader_ok = True
        else:
            print(f"  ❌ tencent loader 返回空数据, {elapsed:.1f}s")
            loader_ok = False
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ❌ tencent loader 失败 ({elapsed:.1f}s): {type(e).__name__}: {e}")
        loader_ok = False

    # 测试3: market_data_tool auto 模式集成
    print("  --- market_data_tool auto 模式 ---")
    import json
    from src.tools.market_data_tool import MarketDataTool

    tool = MarketDataTool()
    t0 = time.time()
    try:
        raw = tool.execute(
            codes=["600519.SH"],
            start_date="2026-09-01",
            end_date="2026-09-04",
            source="auto",
            interval="1D",
        )
        elapsed = time.time() - t0
        data = json.loads(raw)
        provenance = data.get("_provenance", {})
        prov = provenance.get("600519.SH", {})
        actual_source = prov.get("source", "unknown")
        bars = len(data.get("600519.SH", []))
        icon = "✅" if actual_source == "tencent" and bars > 0 else "❌"
        print(f"  {icon} source={actual_source}, bars={bars}, {elapsed:.1f}s")
        tool_ok = actual_source == "tencent" and bars > 0
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ❌ market_data_tool 失败 ({elapsed:.1f}s): {type(e).__name__}: {e}")
        tool_ok = False

    return loader_ok and tool_ok


if __name__ == "__main__":
    main()
