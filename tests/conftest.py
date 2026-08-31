import os
import sys
import inspect
import asyncio

# 将项目根目录加入 sys.path，确保 `import tradingagents` 可用
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: run async test functions with asyncio.run")


def pytest_pyfunc_call(pyfuncitem):
    """Lightweight fallback for async tests when pytest-asyncio is unavailable."""
    if pyfuncitem.config.pluginmanager.hasplugin("asyncio"):
        return None

    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    funcargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_func(**funcargs))
    return True
