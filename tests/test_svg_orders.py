"""Test that order arrows are present in the SVG frames."""

from __future__ import annotations

import asyncio

from diplomacy_agents.enums import Power
from diplomacy_agents.orchestrator import GameOrchestrator, PowerModelMap


def test_svg_contains_orders() -> None:
    """
    Ensure that at least one captured SVG frame contains the <g id="OrderLayer"> element.

    The presence of this group indicates that order arrows were rendered on the board.
    This regresses the bug where move arrows disappeared from animations.
    """
    orch = GameOrchestrator(model_map=PowerModelMap(dict.fromkeys(Power, "random")))

    # Play a single phase – this collects orders and snapshots the board afterwards.
    asyncio.run(orch.play_turn())

    assert orch.svg_frames, "No SVG frames were captured."

    svg_with_orders = any('<g id="OrderLayer"' in svg for svg in orch.svg_frames)
    assert svg_with_orders, "Expected order arrows to be present in at least one SVG frame."
