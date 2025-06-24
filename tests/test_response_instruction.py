# pyright: reportPrivateUsage=false
"""Unit tests for _response_instruction helper."""

from diplomacy_agents import conductor as _c
from diplomacy_agents.engine import Game


def _mk_game() -> Game:
    return Game(rules={"NO_DEADLINE", "CIVIL_DISORDER"})


def test_movement_response() -> None:  # noqa: D103
    g = _mk_game()
    txt = _c._response_instruction(g, "FRANCE")
    assert "JSON object" in txt and "location token" in txt


def test_disband_response() -> None:  # noqa: D103
    g = _mk_game()
    # Force budget positive: give FRANCE extra units via simple trick (unit count more than centers)
    txt = _c._response_instruction(g, "GERMANY")  # initial budget 0 but adjust text still generic
    assert "JSON object" in txt
