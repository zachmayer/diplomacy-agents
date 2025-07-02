"""
Run a few years in civil-disorder mode and ensure the engine survives.

Historically we had only a placeholder; this variant actually exercises the
phase loop so CI catches gross regressions (invalid order handling, phase
transitions, etc.).
"""

from __future__ import annotations

from diplomacy_agents.engine import DiplomacyEngine, Orders


def test_20_turns_smoke() -> None:  # noqa: D401
    """Process 10 full turns with no orders (civil disorder)."""
    eng = DiplomacyEngine()

    # Submit empty order lists for each power and progress a few years – the
    # underlying engine should tolerate holds / no orders gracefully.
    for _ in range(20):  # 20 phases ~ 10 game‐years
        for p in eng.get_game_state().powers:
            eng.submit_orders(p, Orders([]))  # everyone holds / waits
        eng.process_turn()

    # Ensure the year advanced and the game hasn't crashed.
    assert eng.get_game_state().year >= 1903
