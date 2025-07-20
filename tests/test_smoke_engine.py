"""
Run a few years in civil-disorder mode and ensure the engine survives.

The loop submits *no* meaningful orders; every unit implicitly holds / waits.
"""

from __future__ import annotations

from diplomacy_agents.engine import DiplomacyEngine


def test_20_turns_smoke() -> None:
    """Process 20 phases (~10 years) with empty orders – engine should not crash."""
    eng = DiplomacyEngine()

    for _ in range(20):
        # Submit an empty order tuple for every power that still exists.
        for p in eng.supply_center_counts:
            eng.set_orders(p, ())  # everyone holds / waits
        eng.process_turn()

    # Year should have advanced past the starting 1901.
    assert eng.year >= 1903
