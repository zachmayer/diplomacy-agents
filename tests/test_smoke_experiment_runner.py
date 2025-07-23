"""Smoke test for ExperimentRunner with all HoldAgents."""

from typing import cast

from diplomacy_agents.enums import Power
from diplomacy_agents.experiment_runner import ExperimentRunner
from diplomacy_agents.orchestrator import PowerModelMap


def _all_hold_model_map() -> PowerModelMap:
    """Return mapping where every power is controlled by the HoldAgent."""
    return cast(
        PowerModelMap,
        {
            Power.ENGLAND: "hold",
            Power.FRANCE: "hold",
            Power.GERMANY: "hold",
            Power.ITALY: "hold",
            Power.RUSSIA: "hold",
            Power.TURKEY: "hold",
            Power.AUSTRIA: "hold",
        },
    )


def test_experiment_runner_smoke_all_hold() -> None:
    """Run ExperimentRunner once with all HoldAgents to ensure basic execution."""
    runner = ExperimentRunner(messaging_rounds=0, seed=123, max_year=1905)
    result = runner.run_once(model_map=_all_hold_model_map())

    # Basic sanity checks on returned metrics structure
    assert "hash" in result
    for p in (
        Power.ENGLAND,
        Power.FRANCE,
        Power.GERMANY,
        Power.ITALY,
        Power.RUSSIA,
        Power.TURKEY,
        Power.AUSTRIA,
    ):
        assert f"centres_{p}" in result
