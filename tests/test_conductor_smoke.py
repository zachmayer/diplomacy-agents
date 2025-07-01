"""Minimal async smoke test for event-driven conductor."""

import asyncio

from pydantic_ai.models import KnownModelName

from diplomacy_agents.conductor import run_match

# Use a single deterministic model for reproducible tests
TEST_MODELS: tuple[KnownModelName, ...] = ("openai:gpt-4.1-nano-2025-04-14",)


async def _smoke() -> None:
    """Run one-phase smoke test for the stateless conductor."""
    await run_match(max_year=1901, candidate_models=TEST_MODELS)


def test_smoke() -> None:
    """Wrapper for pytest."""
    asyncio.run(_smoke())
