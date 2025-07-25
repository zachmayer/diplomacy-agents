"""
Smoke test – run a few phases with *random* baseline agents only.

Verifies that the orchestrator & baseline agents work without any LLM calls.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import pytest

from diplomacy_agents.orchestrator import GameOrchestrator, HoldModelMap, PowerModelMap, RandomModelMap


@pytest.mark.parametrize("model_map", [HoldModelMap, RandomModelMap])
def test_random_agents_smoke(model_map: PowerModelMap) -> None:
    """Process 5 phases using random agents – should complete without error."""
    orch = GameOrchestrator(model_map=model_map)

    for _ in range(5):
        asyncio.run(orch.play_turn())

    # Game year should be ≥ 1901 (starting year) after five phase advances.
    assert orch.engine.year >= 1901

    # One frame captured at the start of each processed phase.
    assert len(orch.svg_frames) == 5

    # Each SVG frame must parse as valid XML with <svg> root.
    for svg in orch.svg_frames:
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg")
