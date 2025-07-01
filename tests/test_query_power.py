"""Test for _query_power function handling None indices."""

import asyncio
from typing import cast

import pytest

from diplomacy_agents import conductor as _c
from diplomacy_agents.engine import Game, legal_orders, submit_orders
from diplomacy_agents.literals import Power


class _DummyResult:  # noqa: D101
    def __init__(self, output: object) -> None:
        self.output = output


class _DummyAgent:  # noqa: D101
    def __init__(self, *, output_type: type, **_: object) -> None:  # absorb unused kwargs
        self._output_type = output_type

    async def run(self, _: str) -> _DummyResult:  # noqa: D401
        """Return object with an empty selection list."""
        return _DummyResult(self._output_type([]))


def test_query_power_handles_none_indices(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    """_query_power should gracefully skip None indices returned by the model."""
    # Patch the heavy LLM Agent with the lightweight stub
    monkeypatch.setattr(_c, "Agent", _DummyAgent)

    # ------------------------------------------------------------------
    # Construct game state where a power has a build adjustment ---------
    # ------------------------------------------------------------------
    game = Game(rules={"NO_DEADLINE", "CIVIL_DISORDER"})

    # Progress to Fall 1901 Movement
    while not game.get_current_phase().startswith("F1901M"):
        game.process()

    # Russia captures RUM to gain +1 build in Winter 1901
    submit_orders(game, cast(Power, "RUSSIA"), ["F SEV - RUM"])  # type: ignore[arg-type]

    # Resolve to Winter 1901 Adjustments
    while not game.get_current_phase().endswith("A"):
        game.process()

    power: Power = "RUSSIA"
    raw_legal_map = legal_orders(game, power)
    legal_map = {str(loc): opts for loc, opts in raw_legal_map.items()}

    # Run the coroutine under test
    _, orders = asyncio.run(_c._query_power(game, power, "dummy-model", legal_map))  # type: ignore[attr-defined]

    assert orders == []
