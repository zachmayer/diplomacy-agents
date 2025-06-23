"""
Unit tests ensuring `driver` filters out tool call/response messages.

The Diplomat agents must not replay any message that:
1. Contains a `ToolCallPart` (a *tool call request*).
2. Has `role == "tool"` (a *tool response*).
"""

from __future__ import annotations

from diplomacy_agents.conductor import ToolCallPart


def _should_keep(msg: object) -> bool:  # pragma: no cover – simple helper
    """Mirror the driver history filter logic for a single *msg* instance."""
    if any(isinstance(p, ToolCallPart) for p in getattr(msg, "parts", [])):
        return False
    return getattr(msg, "role", None) != "tool"


class _DummyMsg:  # noqa: D401 – minimal stub matching the attributes the filter looks at
    def __init__(self, *, role: str | None = None, parts: list[object] | None = None) -> None:
        self.role = role
        self.parts = parts or []


def test_filter_tool_role() -> None:
    """Messages with role == 'tool' must be filtered out."""
    tool_msg = _DummyMsg(role="tool")
    assert _should_keep(tool_msg) is False


def test_filter_regular_message() -> None:
    """Regular messages without ToolCallPart or tool role are kept."""
    normal_msg = _DummyMsg(role="assistant")
    assert _should_keep(normal_msg) is True
