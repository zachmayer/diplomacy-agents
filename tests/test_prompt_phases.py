# pyright: reportPrivateUsage=false
"""Tests for prompt generation across different phase types."""  # noqa: D100

import logging
import re
import typing

from diplomacy_agents import conductor as _c  # type: ignore[attr-defined]
from diplomacy_agents.engine import Game, submit_orders
from diplomacy_agents.literals import Power

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper to build prompt for a given power
# ---------------------------------------------------------------------------


def build(power: Power, game: Game) -> str:  # noqa: D401,D103
    prompt = _c._build_prompt(game, power)  # type: ignore[attr-defined]
    phase = game.get_current_phase()
    logger.info(f"{phase}, prompt for {power}:\n{prompt}")
    return prompt


# ---------------------------------------------------------------------------
# 1. Movement phase prompt (start of game) -----------------------------------
# ---------------------------------------------------------------------------


def test_prompt_movement_phase() -> None:  # noqa: D103
    game = Game(rules={"NO_DEADLINE", "CIVIL_DISORDER"})
    prompt = build(typing.cast(Power, "FRANCE"), game)

    # Should reference movement phase and list at least one potential order
    assert re.search(r"It is phase S1901M", prompt)
    assert "Potential orders for BRE" in prompt or "Potential orders for PAR" in prompt


# ---------------------------------------------------------------------------
# 2. Retreat phase prompt -----------------------------------------------------
# ---------------------------------------------------------------------------


def _setup_retreat_s1901(game: Game) -> None:
    """Create S1901R retreat for Germany (MUN dislodged)."""
    submit_orders(game, "FRANCE", ["A PAR - BUR"])
    submit_orders(game, "AUSTRIA", ["A VIE - BOH"])
    while not game.get_current_phase().startswith("F1901M"):
        game.process()
    submit_orders(game, "FRANCE", ["A BUR - MUN"])
    submit_orders(game, "AUSTRIA", ["A BOH S A BUR - MUN"])
    while not game.get_current_phase().startswith("F1901R"):
        game.process()


def test_prompt_retreat_phase() -> None:  # noqa: D103
    game = Game(rules={"NO_DEADLINE", "CIVIL_DISORDER"})
    _setup_retreat_s1901(game)
    # Germany now in retreat phase
    prompt = build(typing.cast(Power, "GERMANY"), game)
    assert "It is phase F1901R" in prompt
    # Retreat options should include " R " (retreat) and " D" (disband)
    assert " R " in prompt or " D" in prompt


# ---------------------------------------------------------------------------
# 3. Build phase prompt (+1 build) -------------------------------------------
# ---------------------------------------------------------------------------


def _setup_build_russia(game: Game) -> None:
    """Russia captures RUM to gain +1 build in W1901A."""
    # Spring 1901 – no movement needed
    while not game.get_current_phase().startswith("F1901M"):
        game.process()
    # Fall 1901: fleet SEV to RUM
    submit_orders(game, "RUSSIA", ["F SEV - RUM"])
    while not game.get_current_phase().startswith("W1901A"):
        game.process()


def test_prompt_build_phase() -> None:  # noqa: D103
    game = Game(rules={"NO_DEADLINE", "CIVIL_DISORDER"})
    _setup_build_russia(game)
    prompt = build(typing.cast(Power, "RUSSIA"), game)

    assert "It is phase W1901A" in prompt
    # Expect build guidance text
    assert "build" in prompt.lower()
    # At least one " B" option should exist
    assert " B" in prompt


# ---------------------------------------------------------------------------
# 4. Disband phase prompt (-1 removal) ---------------------------------------
# ---------------------------------------------------------------------------


def _setup_disband_germany(game: Game) -> None:
    """Germany loses MUN and needs to disband one unit."""
    submit_orders(game, "FRANCE", ["A PAR - BUR"])
    submit_orders(game, "AUSTRIA", ["A VIE - BOH"])
    while not game.get_current_phase().startswith("F1901M"):
        game.process()
    submit_orders(game, "FRANCE", ["A BUR - MUN"])
    submit_orders(game, "AUSTRIA", ["A BOH S A BUR - MUN"])
    while not game.get_current_phase().startswith("F1901R"):
        game.process()
    submit_orders(game, "GERMANY", ["A MUN R RUH"])
    while not game.get_current_phase().startswith("W1901A"):
        game.process()


def test_prompt_disband_phase() -> None:  # noqa: D103
    game = Game(rules={"NO_DEADLINE", "CIVIL_DISORDER"})
    _setup_disband_germany(game)
    prompt = build(typing.cast(Power, "GERMANY"), game)
    assert "It is phase W1901A" in prompt
    # Disband instruction and " D" options
    assert "disband" in prompt.lower()
    assert " D" in prompt
