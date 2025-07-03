"""
Smoke test: run a few phases using purely *random* baseline agents.

Ensures orchestrator and baseline agents work without any LLM calls.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

from diplomacy_agents.orchestrator import GameOrchestrator, PowerModelMap


def test_random_agents_smoke() -> None:  # noqa: D401
    """Process 5 phases using random agents – should complete without error."""
    orch = GameOrchestrator(
        model_map=PowerModelMap(
            {
                "AUSTRIA": "random",
                "ENGLAND": "random",
                "FRANCE": "random",
                "GERMANY": "random",
                "ITALY": "random",
                "RUSSIA": "random",
                "TURKEY": "random",
            }
        )
    )

    for _ in range(5):
        asyncio.run(orch._run_single_phase())  # type: ignore[protected-access]

    assert orch.engine.get_game_state().year >= 1901
    # Should have captured 5 frames: one before each of the 5 processed phases
    assert len(orch.engine.svg_frames) == 5

    # Basic XML validity check for each SVG frame.
    for svg in orch.engine.svg_frames:
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg"), "Root element should be <svg>"
