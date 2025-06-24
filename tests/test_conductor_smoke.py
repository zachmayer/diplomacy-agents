"""Minimal async smoke test for event-driven conductor."""

import asyncio

from diplomacy_agents.conductor import run_match

# Default model identifier for tests
DEFAULT_MODEL: str = "openai:gpt-4.1-nano-2025-04-14"


async def _smoke() -> None:
    """Run one-phase smoke test for the stateless conductor."""
    await run_match(model_name=DEFAULT_MODEL, max_phases=1)


def test_smoke() -> None:
    """Wrapper for pytest."""
    asyncio.run(_smoke())
