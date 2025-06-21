"""
Console entry-point for Diplomacy-Agents.

Run `python -m diplomacy_agents.cli self-play` to launch a self-play match where
all seven powers are controlled by identical LLM agents.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping
from pathlib import Path

import click
from pydantic_ai.agent import Agent, AgentRunResult

from diplomacy_agents.agent import DEFAULT_MODEL, Deps, build_agent
from diplomacy_agents.engine import (
    Game,
    broadcast_board_state,
    export_datc,
    snapshot_board,
    to_power,
)
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


async def _self_play(models: Mapping[Power, str] | None = None, seed: int | None = None) -> None:  # noqa: C901
    """Run a full game where each power is controlled by LLM agents in parallel."""
    if seed is not None:
        random.seed(seed)

    rules = {"NO_DEADLINE", "ALWAYS_WAIT", "CD_DUMMIES", "IGNORE_ERRORS"}
    game = Game(rules=rules)

    logger.info("Initial board (classic map):\n%s", game.raw)  # Refer to raw for printable board

    agents: dict[Power, Agent[Deps, str]] = {}
    token_counter: dict[Power, int] = {}

    for p in game.powers:
        model_name = models[p] if models and p in models else DEFAULT_MODEL
        agents[p] = build_agent(game, p, model_name=model_name)
        token_counter[p] = 0

    tick = 0
    while not game.is_game_done:
        tick += 1
        phase = game.get_current_phase()
        logger.info("=== Phase %s (tick %d) ===", phase, tick)

        async def _run_power(pwr: Power, ag: Agent[Deps, str]) -> tuple[Power, AgentRunResult[str]]:
            res = await ag.run("Your move", deps=Deps(game, pwr))
            return pwr, res

        results = await asyncio.gather(*[_run_power(p, a) for p, a in agents.items()])

        for power, result in results:
            usage = result.usage()
            token_counter[power] += usage.total_tokens or 0

        game.process()

        board_state = snapshot_board(game)
        broadcast_board_state(game, board_state)
        logger.info("Broadcast board state to all players")

    logger.info("\n*** Game over – result:\n\n%s", game.raw)

    out_dir = Path("runs")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"final_{int(random.random() * 1e6):06}.json"
    try:
        export_datc(game, out_path)
        logger.info("Saved final game record → %s", out_path)
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not write DATC save file: %s", exc)


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


if __name__ == "__main__":
    cli()
