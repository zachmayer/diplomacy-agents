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
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior

from diplomacy_agents.engine import (
    Game,
    build_orders_model,
    centers,
    centers_by_power,
    export_datc,
    generate_svg_animation,
    legal_orders,
    snapshot_board,
    submit_orders,
    svg_string,
    uncontrolled_centers,
    units,
)
from diplomacy_agents.literals import Power

__all__ = [
    "run_match",
]

logger = logging.getLogger(__name__)


async def _query_power(
    power: Power,
    model_name: str,
    board_state_json: str,
    legal_map: dict[str, list[str]],
    phase: str,
    units_owned: list[str],
    owned_centers: list[str],
    sc_block: str,
    uncontrolled_scs: str,
) -> tuple[Power, list[str]]:
    """
    Run the model for *power* and return its chosen order list.

    The model is asked to emit a *dictionary* mapping each orderable
    location/unit to the integer index of its chosen order.
    """
    output_model = build_orders_model(legal_map)

    # Build a fresh Agent instance constrained by the dynamic model
    agent = Agent(
        model=model_name,
        system_prompt=f"You are playing diplomacy as {power}.",
        output_type=output_model,
        retries=3,
    )

    # ------------------------------------------------------------------
    # Build prompt ------------------------------------------------------
    # ------------------------------------------------------------------

    orders_lines: list[str] = []
    for loc, opts in legal_map.items():
        loc_str = str(loc)
        orders_lines.append(f"Orders for {loc_str}:")
        for i, order in enumerate(opts):
            orders_lines.append(f"{i}. {order}")
        orders_lines.append("")  # blank line between units

    orders_block = "\n".join(orders_lines)

    summary_line = (
        f"You are playing diplomacy. Your goal is to win by controlling 18 supply centers. "
        f"You are power {power}. It is phase {phase}. "
        f"You have {len(units_owned)} unit(s): {', '.join(units_owned) if units_owned else 'none'}. "
        f"You control {len(owned_centers)} supply center(s): {', '.join(owned_centers) if owned_centers else 'none'}."
    )

    prompt = f"""
            <main-goal>
            {summary_line}
            </main-goal>

            <board-state>
            {board_state_json}
            </board-state>

            <supply-centers-by-player>
            {sc_block}
            </supply-centers-by-player>

            <uncontrolled-supply-centers>
            {uncontrolled_scs}
            </uncontrolled-supply-centers>

            <legal-orders>
            {orders_block}
            </legal-orders>

            <response>
            Respond with a JSON object where each key is the location token and each value is the INTEGER index of the chosen order for that location.
            </response>
            """

    logger.debug(prompt)

    chosen_orders: list[str] = []
    try:
        result = await agent.run(prompt)
        for loc, opts in legal_map.items():
            idx: int = cast(int, getattr(result.output, str(loc)))
            chosen_orders.append(opts[idx])
    except UnexpectedModelBehavior:
        chosen_orders = []  # fallback to empty -> HOLD

    return power, chosen_orders


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
            raw_legal_map = legal_orders(game, p)
            # Ensure keys are plain str for type checking
            legal_map: dict[str, list[str]] = {str(k): v for k, v in raw_legal_map.items()}

            # Data for prompt summary ----------------------------------
            phase_name = game.get_current_phase()
            units_map = units(game, p)  # {loc: unit_type}
            units_list: list[str] = [str(loc) for loc in units_map]
            centers_list: list[str] = [str(c) for c in centers(game, p)]

            sc_block = "\n".join(f"{p}: {tuple(str(c) for c in locs)}" for p, locs in centers_by_power(game).items())
            uncontrolled_scs = ", ".join(str(c) for c in uncontrolled_centers(game))

            coros.append(
                _query_power(
                    p,
                    model_name,
                    board_state_json,
                    legal_map,
                    phase_name,
                    units_list,
                    centers_list,
                    sc_block,
                    uncontrolled_scs,
                )
            )

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
