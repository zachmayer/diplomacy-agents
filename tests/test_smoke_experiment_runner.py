"""Smoke test for ExperimentRunner with all HoldAgents."""

from typing import cast

from diplomacy_agents.experiment_runner import ExperimentRunner
from diplomacy_agents.orchestrator import PowerModelMap


def _all_hold_model_map() -> PowerModelMap:
    """Return mapping where every power is controlled by the HoldAgent."""
    return cast(
        PowerModelMap,
        {
            "ENGLAND": "hold",
            "FRANCE": "hold",
            "GERMANY": "hold",
            "ITALY": "hold",
            "RUSSIA": "hold",
            "TURKEY": "hold",
            "AUSTRIA": "hold",
        },
    )


def test_experiment_runner_smoke_all_hold() -> None:
    """Run ExperimentRunner once with all HoldAgents to ensure basic execution."""
    runner = ExperimentRunner(messaging_rounds=0, seed=123, max_year=1905)
    result = runner.run_once(model_map=_all_hold_model_map())

    # Basic sanity checks on returned metrics structure
    assert "hash" in result
    for p in (
        "ENGLAND",
        "FRANCE",
        "GERMANY",
        "ITALY",
        "RUSSIA",
        "TURKEY",
        "AUSTRIA",
    ):
        assert f"centres_{p}" in result
