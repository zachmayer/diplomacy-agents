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
import time
from collections.abc import Awaitable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast, get_args

# Pydantic helpers for the list-of-ints schema
from pydantic import RootModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import KnownModelName

from diplomacy_agents.engine import (
    Game,
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
from diplomacy_agents.literals import MODEL_NAMES, Power

__all__ = [
    "run_match",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt builder -------------------------------------------------------------
# ---------------------------------------------------------------------------


def _sc_counts_line(game: Game) -> str:  # noqa: D401
    """Return pipe-separated counts per power, e.g. ``'FRANCE: 3 | GERMANY: 3'``."""
    return " | ".join(f"{p}: {len(centers(game, p))}" for p in game.powers)


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
    score_line = _sc_counts_line(game)

    # Legal orders – bullet-listed per location ----------------------------
    orders_lines: list[str] = []
    for loc, opts in legal_map.items():
        loc_str = str(loc)
        orders_lines.append(f"Potential orders for {loc_str}:")
        for order in opts:
            orders_lines.append(f"- {order}")
        orders_lines.append("")  # blank line between units

    orders_block = "\n".join(orders_lines)

    support_note = (
        "\nNote that it is legal to support or convoy other powers' units; do so only if it benefits you."
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
    # ------------------------------------------------------------------
    # Select output schema: list[str] with custom validator -------------
    # ------------------------------------------------------------------
    # Dynamically build Literal containing allowed orders
    allowed_orders: tuple[str, ...] = tuple({o for opts in legal_map.values() for o in opts})
    allowed_order_type: type = cast(
        type,
        Literal.__getitem__(allowed_orders),  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
    )

    # Define RootModel for list of allowed order strings
    class OrdersModel(RootModel[list[allowed_order_type]]):
        pass

    output_model = OrdersModel

    # ------------------------------------------------------------------
    # Model invocation --------------------------------------------------
    # ------------------------------------------------------------------
    agent = Agent(
        model=model_name,
        system_prompt=f"You are playing diplomacy as {power}.",
        output_type=output_model,
        retries=1,  # single model invocation retry
        output_retries=3,  # up to three format retries handled by pydantic-ai
        model_settings={"max_tokens": 2048},
    )

    prompt = _build_prompt(game, power)
    logger.debug(prompt)

    t0 = time.perf_counter()
    try:
        result = await agent.run(prompt)
        elapsed = time.perf_counter() - t0
        logger.info("Model %s (%s) completed in %.2fs", model_name, power, elapsed)
        logger.info("Raw output for %s: %s", power, result.output)
    except UnexpectedModelBehavior as e:
        elapsed = time.perf_counter() - t0
        logger.warning("Model %s (%s) failed after %.2fs: %s", model_name, power, elapsed, str(e))
        return power, []

    # Extract the list of order strings from the model output
    output_raw = cast(Any, result.output)
    chosen_orders: list[str] = list(getattr(output_raw, "root", []))

    return power, chosen_orders


def _phase_year(phase_token: str) -> int:  # noqa: D401
    """Extract 4-digit year from phase token like 'S1901M'."""
    return int(phase_token[1:5])


async def run_match(
    *,
    candidate_models: tuple[KnownModelName, ...] | None = None,
    seed: int = 42,
    max_year: int = 1951,
) -> None:
    """
    Run a full self-play Diplomacy match using stateless orchestration.

    Parameters
    ----------
    candidate_models:
        Optional override for the model pool.
    seed:
        RNG seed for reproducibility.
    max_year:
        Optional guard to stop the match after *N* years – useful in tests.

    """
    # ------------------------------------------------------------------
    # Initial setup -----------------------------------------------------
    # ------------------------------------------------------------------

    random.seed(seed)

    # Pick model pool: caller override > default literal list.
    if candidate_models is None:
        candidate_models = MODEL_NAMES

    # Prepare power → model mapping *once* at the start of the game.
    power_to_model: dict[Power, KnownModelName] = {p: random.choice(candidate_models) for p in get_args(Power)}

    logger.info(
        "Power–model assignment: %s",
        ", ".join(f"{p}->{m}" for p, m in power_to_model.items()),
    )

    # ------------------------------------------------------------------
    # Engine initialisation ---------------------------------------------
    # ------------------------------------------------------------------

    # Initialise engine with rules that remove time-outs and CD handling – the
    # conductor decides when to process a phase.
    # https://github.com/diplomacy/diplomacy/blob/df1d0892ce27501386d8dbf2e9948055ea960445/diplomacy/README_RULES.txt#L22
    game = Game(rules={"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"})

    phase_no = 0
    frames: list[str] = []  # in-memory SVG frames
    while not game.is_game_done:
        # Stop if the engine has advanced beyond the requested max_year.
        if _phase_year(game.get_current_phase()) > max_year:
            break

        phase_no += 1

        # Log timing information for this phase tick
        clock_time = datetime.now().strftime("%H:%M:%S")
        game_phase = game.get_current_phase()
        logger.info("=== PHASE TICK %d === Clock: %s | Game: %s ===", phase_no, clock_time, game_phase)

        # Snapshot collected inside prompt builder; external serialisation not needed here

        # Kick off concurrent queries for every power
        coros: list[Awaitable[object]] = []
        # Only query agents for powers that still own at least one centre.
        alive_powers: list[Power] = [p for p in game.powers if len(centers(game, p)) > 0]
        for p in alive_powers:
            raw_legal_map = legal_orders(game, p)
            legal_map: dict[str, list[str]] = {str(k): v for k, v in raw_legal_map.items()}

            # Cast coroutine to Awaitable with explicit result type for Pyright.
            awaitable: Awaitable[object] = _query_power(game, p, power_to_model[p], legal_map)
            coros.append(awaitable)

        results_raw = await asyncio.gather(*coros)
        results: list[tuple[Power, list[str]]] = cast(list[tuple[Power, list[str]]], results_raw)

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

        # Log concise supply-center counts per power.
        logger.info("PHASE %s - %s", game.get_current_phase(), _sc_counts_line(game))

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

    # Movement / Retreat default – array of order strings
    return (
        'Respond with a JSON array of full order strings, e.g. ["A PAR - BUR", "F BRE - MAO"]. '
        "The array length must equal the number of units you currently control and each entry must exactly match one of the legal orders listed above."
    )
