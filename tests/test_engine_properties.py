"""Test the history properties of the engine."""

from __future__ import annotations

from diplomacy_agents.engine import DiplomacyEngine
from diplomacy_agents.enums import OrderResult, Power


def _auto_orders(engine: DiplomacyEngine, power: Power) -> tuple[str, ...]:
    """Pick the first legal order for each orderable unit for *power*."""
    possible = engine.possible_orders[power]
    orders: list[str] = []
    for opts in possible.values():
        if opts:
            orders.append(opts[0])
    return tuple(orders)


def _play_single_phase() -> DiplomacyEngine:
    """Create a game, submit trivial orders, and process one phase."""
    eng = DiplomacyEngine()
    for pwr in eng.powers:
        eng.set_orders(pwr, _auto_orders(eng, pwr))
    eng.process_turn()
    return eng


def test_history_getters_non_empty() -> None:
    """order_history / result_history / state_history populate after one turn."""
    eng = _play_single_phase()

    # Order history ------------------------------------------------------
    orders_hist = eng.order_history
    assert orders_hist, "order_history should not be empty after one processed phase"
    first_phase = next(iter(orders_hist))
    # engine starts at S1901M so that should appear
    assert first_phase.startswith("S1901"), first_phase

    # Result history -----------------------------------------------------
    result_hist = eng.result_history
    assert first_phase in result_hist, "result_history should have same phase key"
    # Each entry maps unit_str → results tuple
    for unit_str, results in result_hist[first_phase].items():
        assert isinstance(unit_str, str)
        assert isinstance(results, tuple)

    # State history ------------------------------------------------------
    state_hist = eng.state_history
    assert first_phase in state_hist, "state_history should include the processed phase"
    simplified = state_hist[first_phase]
    for k in ("units", "centers", "retreats", "builds"):
        assert k in simplified


def test_order_result_enum_usage() -> None:
    """Ensure OrderResult enum values appear in result_history."""
    eng = _play_single_phase()
    for phase_results in eng.result_history.values():
        for results in phase_results.values():
            for res in results:
                assert isinstance(res, OrderResult)
