"""
Phase‐specific order availability tests adapted to the new `DiplomacyEngine` façade.

These are regression-style checks to make sure legal-order generation still
covers retreats, builds and disbands – scenarios that previously required
carefully crafted board positions.
"""

from __future__ import annotations

from diplomacy_agents.engine import DiplomacyEngine, PowerViewDTO

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _advance_until(engine: DiplomacyEngine, phase_prefix: str) -> None:  # noqa: D401
    """Process turns until `engine.phase` starts with *phase_prefix*."""
    while not engine.get_game_state().phase.startswith(phase_prefix):
        engine.process_turn()


# ---------------------------------------------------------------------------
# Scenario 1 – Retreat phase (F1901R) ---------------------------------------
# ---------------------------------------------------------------------------


def _setup_retreat_germany() -> DiplomacyEngine:
    """Create an F1901R retreat scenario for Germany (A MUN dislodged)."""
    eng = DiplomacyEngine()
    # Spring 1901 movement
    eng.submit_orders("FRANCE", ["A PAR - BUR"])
    eng.submit_orders("AUSTRIA", ["A VIE - BOH"])
    _advance_until(eng, "F1901M")  # progress through S1901R to F1901M

    # Fall 1901 movement: BUR supported into MUN
    eng.submit_orders("FRANCE", ["A BUR - MUN"])
    eng.submit_orders("AUSTRIA", ["A BOH S A BUR - MUN"])
    _advance_until(eng, "F1901R")
    return eng


def test_retreat_options_include_retreat_or_disband() -> None:  # noqa: D401
    """Legal orders for Germany in F1901R must include a retreat or disband."""
    eng = _setup_retreat_germany()
    germany: PowerViewDTO = eng.get_power_view("GERMANY")

    # Retreat phase confirmation
    assert germany.phase.endswith("R"), "Expected retreat phase"

    # At least one retreat (" R ") or disband (" D") order should be legal.
    flat = " ".join(germany.orders_list)
    assert " R " in flat or " D" in flat


# ---------------------------------------------------------------------------
# Scenario 2 – Build phase (W1901A) -----------------------------------------
# ---------------------------------------------------------------------------


def _setup_build_russia() -> DiplomacyEngine:
    """Russia captures RUM to earn +1 build in W1901A."""
    eng = DiplomacyEngine()
    _advance_until(eng, "F1901M")  # advance to Fall movement

    eng.submit_orders("RUSSIA", ["F SEV - RUM"])
    _advance_until(eng, "W1901A")
    return eng


def test_build_phase_has_build_orders() -> None:  # noqa: D401
    """Russia should have at least one build order available in W1901A."""
    eng = _setup_build_russia()
    rus: PowerViewDTO = eng.get_power_view("RUSSIA")

    assert rus.phase.startswith("W1901A"), "Expected Winter 1901 adjustments"
    all_orders_flat = rus.orders_list
    assert "build" in " ".join(all_orders_flat).lower() or any(o.endswith(" B") for o in all_orders_flat)


# ---------------------------------------------------------------------------
# Scenario 3 – Disband phase (W1901A with removal) ---------------------------
# ---------------------------------------------------------------------------


def _setup_disband_germany() -> DiplomacyEngine:
    """Germany loses MUN and must remove one unit in W1901A."""
    eng = DiplomacyEngine()
    # Same opening as retreat scenario
    eng.submit_orders("FRANCE", ["A PAR - BUR"])
    eng.submit_orders("AUSTRIA", ["A VIE - BOH"])
    _advance_until(eng, "F1901M")

    eng.submit_orders("FRANCE", ["A BUR - MUN"])
    eng.submit_orders("AUSTRIA", ["A BOH S A BUR - MUN"])
    _advance_until(eng, "F1901R")

    # Retreat Germany to RUH so it still has unit count mismatch later
    eng.submit_orders("GERMANY", ["A MUN R RUH"])
    _advance_until(eng, "W1901A")
    return eng


def test_disband_phase_has_disband_orders() -> None:  # noqa: D401
    """Germany must have a disband/removal option after losing a centre."""
    eng = _setup_disband_germany()
    ger: PowerViewDTO = eng.get_power_view("GERMANY")

    assert ger.phase.startswith("W1901A")
    # Germany should have more units than centers and therefore disband options.
    flat = " ".join(ger.orders_list)
    assert " D" in flat or "disband" in flat.lower()


# Export helpers so snapshot tests can import them without private-usage
# warnings from the type checker.

__all__ = [
    "_setup_retreat_germany",
    "_setup_build_russia",
    "_setup_disband_germany",
]
