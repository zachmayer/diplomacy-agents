# pyright: reportPrivateUsage=false
"""Unit tests for _response_instruction helper."""

from diplomacy_agents import conductor as _c
from diplomacy_agents.engine import Game


def _mk_game() -> Game:
    return Game(rules={"NO_DEADLINE", "CIVIL_DISORDER"})


def test_movement_response() -> None:  # noqa: D103
    g = _mk_game()
    txt = _c._response_instruction(g, "FRANCE")
    assert "JSON array" in txt


def test_disband_response() -> None:  # noqa: D103
    g = _mk_game()
    # Movement phase – expect JSON array guidance as above
    txt = _c._response_instruction(g, "GERMANY")
    assert "JSON array" in txt
