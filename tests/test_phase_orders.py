"""
Phase‑specific order‑availability tests against the refactored `DiplomacyEngine`.

These regression checks ensure that legal‑order generation still covers
retreats, builds and disbands in tricky board positions.
"""

from __future__ import annotations

from diplomacy_agents.engine import DiplomacyEngine
from diplomacy_agents.enums import Power

# ---------------------------------------------------------------------------#
# Helpers                                                                    #
# ---------------------------------------------------------------------------#


def _advance_until(engine: DiplomacyEngine, phase_prefix: str) -> None:
    """Advance the game until `engine.game_state().short_phase` starts with the prefix."""
    while not engine.short_phase.startswith(phase_prefix):
        engine.process_turn()


# ---------------------------------------------------------------------------#
# Scenario 1 – Retreat phase (F1901R)                                        #
# ---------------------------------------------------------------------------#


def _setup_retreat_germany() -> DiplomacyEngine:
    """Create an F1901R retreat scenario where Germany’s A MUN is dislodged."""
    eng = DiplomacyEngine()

    # Spring 1901 movement
    eng.set_orders(Power.FRANCE, ("A PAR - BUR",))
    eng.set_orders(Power.AUSTRIA, ("A VIE - BOH",))
    _advance_until(eng, "F1901M")  # through S1901R to F1901M

    # Fall 1901: BUR + support into MUN
    eng.set_orders(Power.FRANCE, ("A BUR - MUN",))
    eng.set_orders(Power.AUSTRIA, ("A BOH S A BUR - MUN",))
    _advance_until(eng, "F1901R")

    return eng


def test_retreat_options_include_retreat_or_disband() -> None:
    """Legal orders for Germany in F1901R must include a retreat or disband."""
    eng = _setup_retreat_germany()
    assert eng.short_phase.endswith("R"), "Expected retreat phase"

    flat_orders = eng.flat_possible_orders[Power.GERMANY]
    flat = " ".join(flat_orders)
    assert " R " in flat or " D" in flat


# ---------------------------------------------------------------------------#
# Scenario 2 – Build phase (W1901A)                                          #
# ---------------------------------------------------------------------------#


def _setup_build_russia() -> DiplomacyEngine:
    """Russia captures RUM to earn +1 build in W1901A."""
    eng = DiplomacyEngine()
    _advance_until(eng, "F1901M")

    eng.set_orders(Power.RUSSIA, ("F SEV - RUM",))
    _advance_until(eng, "W1901A")
    return eng


def test_build_phase_has_build_orders() -> None:
    """Russia should have at least one build order available in W1901A."""
    eng = _setup_build_russia()
    assert eng.short_phase.startswith("W1901A"), "Expected Winter 1901 adjustments"
    rus_flat = eng.flat_possible_orders[Power.RUSSIA]
    flat = " ".join(rus_flat).lower()
    assert "build" in flat or any(o.endswith(" B") for o in rus_flat)


# ---------------------------------------------------------------------------#
# Scenario 3 – Disband phase (W1901A with removal)                           #
# ---------------------------------------------------------------------------#


def _setup_disband_germany() -> DiplomacyEngine:
    """Germany loses MUN and must remove one unit in W1901A."""
    eng = DiplomacyEngine()

    # Same opening as retreat scenario
    eng.set_orders(Power.FRANCE, ("A PAR - BUR",))
    eng.set_orders(Power.AUSTRIA, ("A VIE - BOH",))
    _advance_until(eng, "F1901M")

    eng.set_orders(Power.FRANCE, ("A BUR - MUN",))
    eng.set_orders(Power.AUSTRIA, ("A BOH S A BUR - MUN",))
    _advance_until(eng, "F1901R")

    # Retreat Germany to RUH so it still has unit‑count mismatch later
    eng.set_orders(Power.GERMANY, ("A MUN R RUH",))
    _advance_until(eng, "W1901A")
    return eng


def test_disband_phase_has_disband_orders() -> None:
    """Germany must receive disband options after losing a centre."""
    eng = _setup_disband_germany()
    assert eng.short_phase.startswith("W1901A")
    ger_flat = eng.flat_possible_orders[Power.GERMANY]
    flat = " ".join(ger_flat).lower()
    assert " d" in flat or "disband" in flat


# Export helpers for snapshot tests without triggering private‑usage warnings.
__all__ = [
    "_setup_retreat_germany",
    "_setup_build_russia",
    "_setup_disband_germany",
]
