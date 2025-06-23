"""
Console entry-point for Diplomacy-Agents.

Run `python -m diplomacy_agents.cli self-play` to launch a self-play match where
all seven powers are controlled by identical LLM agents.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Coroutine, Mapping
from typing import Any

import click

from diplomacy_agents.agent import DEFAULT_MODEL, build_agent
from diplomacy_agents.conductor import GameManager, GameRPC, driver
from diplomacy_agents.engine import to_power
from diplomacy_agents.literals import Power

# ---------------------------------------------------------------------------
# Logging setup --------------------------------------------------------------
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("cli")

# ---------------------------------------------------------------------------
# Internal helpers -----------------------------------------------------------
# ---------------------------------------------------------------------------


async def _self_play(models: Mapping[Power, str] | None = None, seed: int | None = None) -> None:  # noqa: D401, ARG001
    """Emit warning that legacy self-play is deprecated."""
    if seed is not None:
        random.seed(seed)
    logger.error("Legacy self_play is deprecated – use 'conductor' command instead.")


# ---------------------------------------------------------------------------
# Click commands -------------------------------------------------------------
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:  # noqa: D401  (simple grouping command)
    """Diplomacy-Agents command-line tools."""


@cli.command("self-play", help="Run a full self-play Diplomacy match with LLM agents.")
@click.option(
    "--seed",
    type=int,
    default=None,
    help="RNG seed for reproducibility.",
)
@click.option(
    "--model",
    "models_opt",
    multiple=True,
    help="Override model for a specific power, e.g. --model FRANCE=openai:gpt-4.1-nano-2025-04-14",
)
def self_play_cmd(seed: int | None, models_opt: tuple[str, ...]) -> None:  # noqa: D401
    """Thin wrapper around the async self-play driver."""
    models: dict[Power, str] | None = None
    if models_opt:
        models = {}
        for mapping in models_opt:
            if "=" not in mapping:
                raise click.BadParameter("MODEL overrides must be in the form POWER=ModelName")
            power_token, model_name = mapping.split("=", 1)
            power_typed = to_power(power_token)
            models[power_typed] = model_name

    asyncio.run(_self_play(models=models, seed=seed))


@cli.command("conductor", help="Run self-play via event-driven conductor.")
@click.option("--seed", type=int, default=42, help="RNG seed for reproducibility.")
def conductor_cmd(seed: int) -> None:  # noqa: D401
    """Launch the event-driven self-play match."""

    async def _run() -> None:
        gm = GameManager(seed=seed)
        tasks: list[asyncio.Task[None]] = []
        for p in gm.game.powers:
            rpc = GameRPC(power=p, gm=gm)
            agent_obj = build_agent(rpc, model_name=DEFAULT_MODEL)
            coro: Coroutine[Any, Any, None] = driver(agent_obj, gm.inboxes[p], rpc)
            tasks.append(asyncio.create_task(coro))
        await asyncio.gather(*tasks)

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
