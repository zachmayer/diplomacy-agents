"""
Stateless conductor for Diplomacy-Agents.

This module implements the *new* simplified match driver requested by the
project refactor.  Key characteristics:

1. No event broadcasting, no per-power inbox traffic.
2. Each LLM agent is called exactly *once* per phase.
3. The agent receives the *full* board state as the **user** message.
4. The agent must respond with a list of order strings (``list[str]``).
5. Whatever the agent returns is submitted to the diplomacy engine verbatim –
   illegal orders are silently converted to ``HOLD`` by the engine.
6. All seven powers are queried *concurrently* via ``asyncio.gather``.
7. After every phase the conductor prints which powers are still active vs.
   eliminated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, create_model
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior

from diplomacy_agents.engine import (
    Game,
    centers,
    ensure_str_list,
    export_datc,
    generate_svg_animation,
    legal_orders,
    snapshot_board,
    submit_orders,
    svg_string,
)
from diplomacy_agents.literals import Power

__all__ = [
    "run_match",
]

logger = logging.getLogger(__name__)


def _build_output_model(legal_opts: list[str]) -> type[BaseModel]:  # noqa: D401
    """Return an object schema with `orders` list constrained to literals."""
    if not legal_opts:
        return create_model("OrdersEmpty", orders=(list[str], ...))

    order_literal = Literal[tuple(legal_opts)]
    return create_model("OrdersObj", orders=(list[order_literal], ...))


async def _query_power(
    power: Power,
    model_name: str,
    board_state_json: str,
    legal_opts: list[str],
) -> tuple[Power, list[str]]:
    """Run the model for *power* and return its chosen orders."""
    output_model = _build_output_model(legal_opts)

    # Build a fresh Agent instance constrained by the dynamic model
    agent = Agent(
        model=model_name,
        system_prompt=f"You are playing diplomacy as {power}.",
        output_type=output_model,
        retries=3,
    )

    prompt = f"""
            <main-goal>
            You are playing diplomacy. You are power {power}. Your goal is to win.
            </main-goal>

            <board-state>
            The current board state is:
            {board_state_json}
            </board-state>

            <legal-orders>
            Your legal orders are:
            {legal_opts}
            </legal-orders>

            <response>
            Respond with a list of legal orders.
            Your response must be a list of strings.
            Each string must come from the legal orders above.
            </response>
            """
    logger.debug(prompt)
    try:
        result = await agent.run(prompt)
        orders_attr = cast(list[object], getattr(result.output, "orders", []))
        orders_list = ensure_str_list(orders_attr)
    except UnexpectedModelBehavior:
        orders_list = []  # fallback to empty -> HOLD

    return power, orders_list


async def run_match(
    *,
    model_name: str,
    seed: int = 42,
    max_phases: int = 100,
) -> None:
    """
    Run a full self-play Diplomacy match using stateless orchestration.

    Parameters
    ----------
    model_name:
        Identifier understood by Pydantic-AI, e.g. ``"openai:gpt-4o-mini"``.
    seed:
        RNG seed for reproducibility.
    max_phases:
        Optional guard to stop the match after *N* phases – useful in tests.

    """
    random.seed(seed)

    # Initialise engine with rules that remove time-outs and CD handling – the
    # conductor decides when to process a phase.
    # https://github.com/diplomacy/diplomacy/blob/df1d0892ce27501386d8dbf2e9948055ea960445/diplomacy/README_RULES.txt#L22
    game = Game(rules={"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"})

    phase_no = 0
    frames: list[str] = []  # in-memory SVG frames
    while not game.is_game_done:
        phase_no += 1
        if phase_no > max_phases:
            break

        # Serialise the current board state once and share across agents.
        board_state_data = snapshot_board(game).model_dump()
        board_state_json = json.dumps(board_state_data, indent=2, sort_keys=True)

        # Kick off concurrent queries for every power
        coros: list[Awaitable[tuple[Power, list[str]]]] = []
        # Only query agents for powers that still own at least one centre.
        alive_powers: list[Power] = [p for p in game.powers if len(centers(game, p)) > 0]
        for p in alive_powers:
            legal_map = legal_orders(game, p)
            legal_flat = [o for arr in legal_map.values() for o in arr]
            coros.append(_query_power(p, model_name, board_state_json, legal_flat))

        results = await asyncio.gather(*coros)

        # Submit whatever orders the model produced.
        for pwr, orders in results:
            if orders:
                ok = submit_orders(game, pwr, orders)
                if not ok:
                    logger.warning("Invalid orders from %s dropped: %s", pwr, orders)

        # Capture frame BEFORE processing so order arrows are visible
        pre_process_svg = svg_string(game)
        frames.append(pre_process_svg)

        # Advance the game to resolve the phase
        game.process()

        # ------------------------------------------------------------------
        # Persist artefacts – overwrite same filenames each phase ------------
        # ------------------------------------------------------------------

        # DATC save after processing (post-state)
        save_dir = Path("game_saves")
        save_dir.mkdir(exist_ok=True)
        export_datc(game, save_dir / "game_state.datc")

        # 2) Animated SVG aggregating all frames so far
        svg_text = svg_string(game)
        frames.append(svg_text)

        animate_dir = Path("board_svg")
        animate_dir.mkdir(exist_ok=True)
        animate_path = animate_dir / "board_animation.svg"
        generate_svg_animation(frames, animate_path)

        # Compute status report.
        active = [p for p in game.powers if len(centers(game, p)) > 0]
        eliminated = [p for p in game.powers if p not in active]
        logger.info(
            "PHASE %s - ACTIVE: %s | ELIMINATED: %s",
            game.get_current_phase(),
            active,
            eliminated,
        )

    logger.info("Game finished after %d phase(s).", phase_no)
