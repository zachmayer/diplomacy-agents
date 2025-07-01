"""
Console entry-point for Diplomacy-Agents.

Run `python -m diplomacy_agents.cli self-play` to launch a self-play match where
all seven powers are controlled by identical LLM agents.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, cast

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
# Click commands -------------------------------------------------------------
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:  # noqa: D401  (simple grouping command)
    """Diplomacy-Agents command-line tools."""


@cli.command("conductor", help="Run self-play via the stateless conductor.")
@click.option("--seed", type=int, default=42, help="RNG seed for reproducibility.")
@click.option(
    "--max-year",
    type=int,
    default=1951,
    help="Stop the match after the given game year (inclusive).",
)
def conductor_cmd(seed: int, max_year: int) -> None:  # noqa: D401
    """Launch the stateless self-play match."""
    coro = cast(
        Coroutine[Any, Any, None],
        run_match(
            seed=seed,
            max_year=max_year,
        ),
    )
    asyncio.run(coro)


if __name__ == "__main__":
    cli()
