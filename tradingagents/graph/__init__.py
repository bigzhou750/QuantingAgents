# zhitouagent/graph/__init__.py

from .trading_graph import zhitouagentGraph

# Compatibility export for existing integrations; product-facing text uses zhitouagent.
TradingAgentsGraph = zhitouagentGraph
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

__all__ = [
    "zhitouagentGraph",
    "TradingAgentsGraph",
    "ConditionalLogic",
    "GraphSetup",
    "Propagator",
    "Reflector",
    "SignalProcessor",
]
