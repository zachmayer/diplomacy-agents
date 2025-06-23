"""Minimal async smoke test for event-driven conductor."""

import asyncio

from diplomacy_agents.agent import DEFAULT_MODEL, build_agent
from diplomacy_agents.conductor import GameManager, GameRPC, driver


async def _smoke() -> None:
    """Start one agent and verify phase string is non-empty after 0.3s."""
    gm = GameManager()
    pwr = gm.game.powers[0]
    rpc = GameRPC(power=pwr, gm=gm)
    agent_obj = build_agent(rpc, model_name=DEFAULT_MODEL)
    asyncio.create_task(driver(agent_obj, gm.inboxes[pwr], rpc))
    await asyncio.sleep(0.3)
    # Ensure phase string exists (e.g., "S1901M")
    assert gm.game.get_current_phase()


def test_smoke() -> None:
    """Wrapper for pytest."""
    asyncio.run(_smoke())
