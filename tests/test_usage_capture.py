"""Unit test verifying that ``LLMAgent`` records token usage internally after an LLM call."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.usage import Usage

# We now track usage per-agent instead of a global list.
from diplomacy_agents.agents import LLMAgent
from diplomacy_agents.literals import Power


class _StubModel:
    """Minimal stub mimicking the return value of ``pydantic_ai.models.infer_model``."""

    class _Profile:
        supports_json_schema_output = False

    profile = _Profile()


class _StubResult:
    """Minimal stub mimicking pydantic-ai Agent result object."""

    def __init__(self) -> None:
        self.output = "OK"
        self._usage = Usage(request_tokens=10, response_tokens=5, total_tokens=15)

    def usage(self) -> Usage:
        return self._usage


class _StubAgent:
    """Replaces the real *pydantic_ai* Agent during the test."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Ignore all constructor parameters – stub only."""

    async def run(self, _prompt: str) -> _StubResult:
        """Return a dummy result with fixed usage counts."""
        return _StubResult()


def _dummy_state_view() -> tuple[SimpleNamespace, SimpleNamespace]:
    # Create minimal dummy objects with required attributes for get_orders.
    state = SimpleNamespace()
    view = SimpleNamespace()
    view.orders_list = ["A PAR H"]
    return state, view


# Helper to satisfy type checkers (explicit return type).


def _infer_model_stub(*_args: object, **_kw: object) -> _StubModel:
    """Return a fresh stub model instance (patched over infer_model)."""
    return _StubModel()


def test_stats_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that LLMAgent records usage internally after an LLM call."""
    # Patch Agent class inside module.
    from diplomacy_agents import agents as agents_mod

    monkeypatch.setattr(agents_mod, "Agent", _StubAgent)
    # Prevent real model inference that would hit external services.
    monkeypatch.setattr(agents_mod.models, "infer_model", _infer_model_stub)

    agent = LLMAgent(Power.ENGLAND, "openai:gpt-4.1")

    _ = _dummy_state_view()

    asyncio.run(agent._run_llm(prompt="hi", output_type=str))  # pyright: ignore[reportPrivateUsage]

    # Verify token aggregation happened.
    totals = agent.token_totals["openai:gpt-4.1"]
    assert totals["request_tokens"] == 10 and totals["response_tokens"] == 5
