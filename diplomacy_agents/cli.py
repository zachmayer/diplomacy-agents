"""
Console entry-point for Diplomacy-Agents.

Run `python -m diplomacy_agents.cli self-play` to launch a self-play match where
all seven powers are controlled by identical LLM agents.
"""

import logging

import click

from diplomacy_agents.experiment_runner import ExperimentRunner
from diplomacy_agents.logging_config import setup_logging

# Configure root logger once for the CLI entry-point.
setup_logging()

# Silence noisy third-party loggers.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("diplomacy").setLevel(logging.INFO)

logger = logging.getLogger("cli")


@click.group()
def cli() -> None:
    """Diplomacy-Agents command-line tools."""


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
    import asyncio

    async def run_experiments() -> None:
        for i in range(1, runs + 1):
            runner = ExperimentRunner(seed=seed)
            await runner.run_once()
            logger.info("[%d/%d] completed experiment", i, runs)

    asyncio.run(run_experiments())


if __name__ == "__main__":
    cli()
