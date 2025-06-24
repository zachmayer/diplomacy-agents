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
    export_datc,
    generate_svg_animation,
    legal_orders,
    phase_long,
    phase_type,
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


# ---------------------------------------------------------------------------
# Prompt builder -------------------------------------------------------------
# ---------------------------------------------------------------------------


def _build_prompt(
    game: Game,
    power: Power,
) -> str:
    """Return formatted XML prompt for *power* covering current game context."""
    # Build board snapshot and legal orders dynamically
    board_state_json = json.dumps(snapshot_board(game).model_dump(), indent=2, sort_keys=True)
    legal_map: dict[str, list[str]] = {str(loc): orders for loc, orders in legal_orders(game, power).items()}

    # Data
    phase = game.get_current_phase()
    phase_long_txt = phase_long(game)
    units_map = units(game, power)
    units_owned: list[str] = [f"{ut} {loc}" for loc, ut in units_map.items()]
    owned_centers: list[str] = [str(c) for c in centers(game, power)]
    uncontrolled_scs = ", ".join(str(c) for c in uncontrolled_centers(game))
    score_line = " | ".join(f"{p}: {len(centers(game, p))}" for p in game.powers)

    # Legal orders – numbered per location ----------------------------
    orders_lines: list[str] = []
    for loc, opts in legal_map.items():
        loc_str = str(loc)
        orders_lines.append(f"Potential orders for {loc_str}:")
        for i, order in enumerate(opts):
            orders_lines.append(f"{i}. {order}")
        orders_lines.append("")  # blank line between units

    orders_block = "\n".join(orders_lines)

    support_note = (
        "\nNote that it is legal both support and convoy other powers' units. Only do this if it is to your advantage."
        if phase_type(game) == "M"
        else ""
    )

    response_text = _response_instruction(game, power)

    prompt = f"""

<main-goal>
You are playing diplomacy. Your goal is to win by controlling 18 or more supply centers.
</main-goal>

<who-am-i>
You are power {power}.
</who-am-i>

<supply-center-counts>
{score_line}

Remember: the first power to control 18 supply centers wins the game.
</supply-center-counts>

<game-state>
It is phase {phase}: {phase_long_txt}.

You have {len(units_owned)} unit(s): {", ".join(units_owned) if units_owned else "none"}.

You control {len(owned_centers)} supply center(s): {", ".join(owned_centers) if owned_centers else "none"}.

The uncontrolled supply center(s) are: {uncontrolled_scs}.

The full board state is:
{board_state_json}

Note the location of both the other power's units and supply centers. Both are critical to your strategy.
</game-state>

<legal-orders>
Your legal orders are:

{orders_block}
{support_note}
</legal-orders>

<response>
{response_text}
</response>
"""

    return prompt


async def _query_power(
    game: Game,
    power: Power,
    model_name: str,
    legal_map: dict[str, list[str]],
) -> tuple[Power, list[str]]:
    """
    Run the model for *power* and return its chosen order list.

    The model is asked to emit a *dictionary* mapping each orderable
    location/unit to the integer index of its chosen order.
    """
    output_model = build_orders_model(legal_map, adjustment=(game.get_current_phase()[-1] == "A"))

    # Build a fresh Agent instance constrained by the dynamic model
    agent = Agent(
        model=model_name,
        system_prompt=f"You are playing diplomacy as {power}.",
        output_type=output_model,
        retries=3,
    )

    prompt = _build_prompt(game, power)

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
    max_phases: int = 1000,
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

        # Snapshot collected inside prompt builder; external serialisation not needed here

        # Kick off concurrent queries for every power
        coros: list[Awaitable[tuple[Power, list[str]]]] = []
        # Only query agents for powers that still own at least one centre.
        alive_powers: list[Power] = [p for p in game.powers if len(centers(game, p)) > 0]
        for p in alive_powers:
            raw_legal_map = legal_orders(game, p)
            legal_map: dict[str, list[str]] = {str(k): v for k, v in raw_legal_map.items()}

            coros.append(
                _query_power(
                    game,
                    p,
                    model_name,
                    legal_map,
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


# ---------------------------------------------------------------------------
# Response text helper -------------------------------------------------------
# ---------------------------------------------------------------------------


def _response_instruction(game: Game, power: Power) -> str:
    """Return <response> guidance string based on current game phase and build/disband budget."""
    game.get_current_phase()
    pt = phase_type(game)

    if pt == "A":
        units_owned = len(units(game, power))
        centers_owned = len(centers(game, power))
        budget = units_owned - centers_owned

        if budget > 0:
            return (
                f"You must disband exactly {budget} unit(s). Respond with a JSON object containing {budget} key-value pairs. "
                "Each key is the LOCATION token of the unit you are disbanding and its value is the INTEGER index (usually 0) of the chosen '... D' order. "
                "Omit all other locations."
            )
        if budget < 0:
            n = -budget
            return f"You may build up to {n} unit(s). Respond with a JSON object containing {n} key-value pairs (build location → index). "
        return "You have no adjustments to make. Respond with an empty JSON object {}."

    # Movement / Retreat default
    return "Respond with a JSON object where each key is the location token and each value is the INTEGER index of the chosen order for that location."
