"""QuantingAgents policy for embedded Vibe tools."""

from __future__ import annotations

HIGH_RISK_TOOL_NAMES = frozenset(
    {
        "bash",
        "background_run",
        "cancel_background",
        "write_file",
        "edit_file",
        "save_skill",
        "patch_skill",
        "delete_skill",
        "trading_place_order",
        "trading_cancel_order",
        "etoro_cancel_close_order",
        "etoro_close_position",
        "etoro_copy_close",
        "etoro_copy_start",
        "etoro_edit_position_stops",
    }
)


def disabled_tool_names() -> frozenset[str]:
    """Return tools disabled for the networked QuantingAgents workbench."""
    return HIGH_RISK_TOOL_NAMES
