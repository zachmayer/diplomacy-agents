"""Smoke test for ExperimentRunner with all HoldAgents."""

import pytest

from diplomacy_agents.enums import Power
from diplomacy_agents.experiment_runner import ExperimentRunner
from diplomacy_agents.orchestrator import HoldModelMap, PowerModelMap, RandomModelMap


@pytest.mark.parametrize("model_map", [HoldModelMap, RandomModelMap])
def test_experiment_runner_smoke(model_map: PowerModelMap) -> None:
    """Run ExperimentRunner once with all HoldAgents to ensure basic execution."""
    runner = ExperimentRunner(seed=123, max_year=1905)
    result = runner.run_once(model_map=model_map)

    # Basic sanity checks on returned metrics structure
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
