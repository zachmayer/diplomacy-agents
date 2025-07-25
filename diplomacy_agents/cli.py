"""
Console entry-point for Diplomacy-Agents.

Run `python -m diplomacy_agents.cli self-play` to launch a self-play match where
all seven powers are controlled by identical LLM agents.
"""

import json
import logging
from pathlib import Path

import click

from diplomacy_agents.experiment_runner import ExperimentRunner
from diplomacy_agents.logging_config import setup_logging
from diplomacy_agents.orchestrator import PowerModelMap, run_game

# ---------------------------------------------------------------------------
# Logging setup --------------------------------------------------------------
# ---------------------------------------------------------------------------

# Configure root logger once for the CLI entry-point.
setup_logging()

# Silence noisy third-party loggers.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("diplomacy").setLevel(logging.INFO)

logger = logging.getLogger("cli")

# ---------------------------------------------------------------------------
# Click commands -------------------------------------------------------------
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """Diplomacy-Agents command-line tools."""


@cli.command("play", help="Run a complete self-play match with a provided model map JSON.")
@click.option(
    "--model-map",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to a JSON file mapping powers to model names.",
)
def play(model_map: str) -> None:
    """Run the orchestrator with an explicit model map JSON file."""
    data = json.loads(Path(model_map).read_text())
    run_game(model_map=PowerModelMap(**data))


# ---------------------------------------------------------------------------
# Batch experiments command --------------------------------------------------
# ---------------------------------------------------------------------------


@cli.command("experiments", help="Run multiple self-play experiments and append to results.csv.")
@click.option("--runs", type=int, default=10, show_default=True, help="Number of experiments to run.")
@click.option(
    "--seed",
    type=int,
    default=42,
    show_default=True,
    help="Random seed for model assignment reproducibility.",
)
def experiments(runs: int, seed: int) -> None:
    """Execute *runs* experiments via ExperimentRunner."""
    runner = ExperimentRunner(seed=seed, max_year=1905)

    for i in range(1, runs + 1):
        runner.run_once()
        logger.info("[%d/%d] completed experiment", i, runs)


if __name__ == "__main__":
    cli()
