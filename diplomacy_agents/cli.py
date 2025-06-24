"""
Console entry-point for Diplomacy-Agents.

Run `python -m diplomacy_agents.cli self-play` to launch a self-play match where
all seven powers are controlled by identical LLM agents.
"""

from __future__ import annotations

import asyncio
import logging

import click

from diplomacy_agents.conductor import run_match

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
# Internal helpers -----------------------------------------------------------
# ---------------------------------------------------------------------------

# Local default model identifier
DEFAULT_MODEL: str = "openai:gpt-4.1-nano"

# ---------------------------------------------------------------------------
# Click commands -------------------------------------------------------------
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:  # noqa: D401  (simple grouping command)
    """Diplomacy-Agents command-line tools."""


@cli.command("conductor", help="Run self-play via the stateless conductor.")
@click.option("--seed", type=int, default=42, help="RNG seed for reproducibility.")
@click.option(
    "--max-phases",
    type=int,
    default=1000,
    help="Stop the match after N phases (useful for smoke tests).",
)
def conductor_cmd(seed: int, max_phases: int) -> None:  # noqa: D401
    """Launch the stateless self-play match."""
    asyncio.run(
        run_match(
            model_name=DEFAULT_MODEL,
            seed=seed,
            max_phases=max_phases,
        )
    )


if __name__ == "__main__":
    cli()
