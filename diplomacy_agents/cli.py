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
logger = logging.getLogger("cli")

# ---------------------------------------------------------------------------
# Click commands -------------------------------------------------------------
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:  # noqa: D401  (simple grouping command)
    """Diplomacy-Agents command-line tools."""


@cli.command("play", help="Run a complete self-play match with random models.")
@click.option("--seed", type=int, default=42, help="RNG seed for reproducibility.")
def play_cmd(seed: int) -> None:  # noqa: D401
    """Run the simplified orchestrator and print final SC counts."""
    final_sc = run_game(seed=seed)
    ordered = sorted(final_sc.items(), key=lambda x: x[1], reverse=True)
    for _power, _count in ordered:
        pass


if __name__ == "__main__":
    cli()
