"""
Console entry-point for Diplomacy-Agents.

Run `python -m diplomacy_agents.cli self-play` to launch a self-play match where
all seven powers are controlled by identical LLM agents.
"""

import logging

import click

from diplomacy_agents.orchestrator import run_game

# ---------------------------------------------------------------------------
# Logging setup --------------------------------------------------------------
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("diplomacy").setLevel(logging.INFO)
logger = logging.getLogger("cli")

# ---------------------------------------------------------------------------
# Click commands -------------------------------------------------------------
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:  # noqa: D401  (simple grouping command)
    """Diplomacy-Agents command-line tools."""


@cli.command("play", help="Run a complete self-play match with random models.")
@click.option("--seed", type=int, default=42, help="RNG seed for reproducibility.")
@click.option(
    "--message-rounds",
    "messaging_rounds",
    type=int,
    default=0,
    show_default=True,
    help="Number of press rounds per movement phase (0 disables press).",
)
def play(seed: int, messaging_rounds: int) -> None:  # noqa: D401
    """Run the orchestrator and print final SC counts."""
    run_game(seed=seed, messaging_rounds=messaging_rounds)


if __name__ == "__main__":
    cli()
