"""
Smoke test: run a few phases using purely *random* baseline agents.

Ensures orchestrator and baseline agents work without any LLM calls.
"""

from __future__ import annotations

import asyncio

from diplomacy_agents.engine import PowerModelMap
from diplomacy_agents.orchestrator import GameOrchestrator


def test_random_agents_smoke() -> None:  # noqa: D401
    """Process 5 phases using random agents – should complete without error."""
    orch = GameOrchestrator(
        model_map=PowerModelMap(
            AUSTRIA="random",
            ENGLAND="random",
            FRANCE="random",
            GERMANY="random",
            ITALY="random",
            RUSSIA="random",
            TURKEY="random",
        )
    )

    for _ in range(5):
        asyncio.run(orch._run_single_phase())  # type: ignore[protected-access]

    assert orch.engine.get_game_state().year >= 1901
