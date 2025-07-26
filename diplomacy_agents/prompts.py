"""Prompt-construction helpers for Diplomacy LLM agents."""

import json
import logging
import uuid
from collections.abc import Callable, Mapping, Sized
from pathlib import Path
from typing import TypeGuard, TypeVar

# Third-party
from token_count import TokenCount

# Internal imports
from diplomacy_agents.engine import DiplomacyEngine
from diplomacy_agents.enums import PhaseType, Power

# ---------------------------------------------------------------------------
# Global utilities
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

_TOKEN_COUNTER = TokenCount(model_name="gpt-4o")


def _count_tokens(text: str) -> int:
    """Return a fast, approximate token count for *text*."""
    return int(_TOKEN_COUNTER.num_tokens_from_string(text))


# ---------------------------------------------------------------------------
# Helper for persisting oversized prompts                                    #
# ---------------------------------------------------------------------------


def _persist_long_prompt(  # pragma: no cover
    prompt: str,
    short_phase: str,
    power: "Power",
    token_count: int,
) -> None:
    """Write *prompt* to ``artifacts/long_prompts`` and emit a warning."""
    logger.warning(
        "Orders prompt for %s/%s is extremely long: %d tokens",
        short_phase,
        power,
        token_count,
    )

    out_dir = Path("artifacts") / "long_prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{short_phase}_{power}_{uuid.uuid4().hex}.xml"
    try:
        file_path.write_text(prompt)
    except Exception as exc:  # Pragmatic best-effort logging
        logger.error("Failed to persist long prompt to %s: %s", file_path, exc)


# Public re-exports ----------------------------------------------------

__all__: list[str] = [
    "build_orders_prompt",
]


K = TypeVar("K", bound=str)


def is_empty(x: object) -> bool:
    return x is None or (isinstance(x, Sized) and len(x) == 0)


def is_mapping(x: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(x, Mapping)


def prune_empty_keys[K: str](d: Mapping[K, object]) -> dict[K, object]:
    cleaned: dict[K, object] = {}
    for k, v in d.items():
        if is_mapping(v):
            v = prune_empty_keys(v)
        if not is_empty(v):
            cleaned[k] = v
    return cleaned


def dump_dict[K: str, V](d: Mapping[K, V]) -> str:
    """Pretty‑print *any* mapping after pruning empty values."""
    return json.dumps(prune_empty_keys(d), indent=2, sort_keys=True, default=str)


def _adjustment_guidance(engine: DiplomacyEngine, power: Power) -> str:
    """Guidance for Adjustment (build / disband) phases."""
    diff = engine.supply_center_counts[power] - len(engine.units[power])
    if diff > 0:
        return f"You have **{diff} build(s)**. Return exactly {diff} distinct build order(s)."
    if diff < 0:
        removes = -diff
        return f"You must **disband {removes} unit(s)**. Return exactly {removes} disband order(s)."
    return "No builds or removals required; return an empty list."


def _movement_guidance(_engine: DiplomacyEngine, _power: "Power") -> str:
    """Guidance for Movement phases."""
    return "Issue one legal order to each of your units. Units without orders will *hold*."


def _retreat_guidance(engine: DiplomacyEngine, power: Power) -> str:
    """Guidance for Retreat phases."""
    pending = len(engine.possible_orders[power])
    return f"You have **{pending} dislodged unit(s)**. Return exactly {pending} retreat **or** disband order(s)."


# Map phase-code → guidance generator (functions take engine, power)
_PHASE_GUIDE: dict[str, Callable[[DiplomacyEngine, "Power"], str]] = {
    PhaseType.MOVEMENT: _movement_guidance,
    PhaseType.RETREAT: _retreat_guidance,
    PhaseType.ADJUSTMENT: _adjustment_guidance,
}


def build_orders_prompt(engine: DiplomacyEngine, power: "Power", phases_back: int = 2) -> str:
    """Return the full instruction prompt for orders generation."""
    guidance_fn = _PHASE_GUIDE.get(str(engine.phase_type), lambda _e, _p: "")
    guidance = guidance_fn(engine, power)

    home_centers = tuple(sorted(engine.home_supply_centers[power]))
    owned_centers = tuple(sorted(engine.supply_centers[power]))
    phases = list(engine.state_history.keys())[-phases_back:][::-1]

    order_history = {phase: engine.order_history[phase] for phase in phases}
    result_history = {phase: engine.result_history[phase] for phase in phases}
    state_history = {phase: engine.state_history[phase] for phase in phases}

    prompt: str = f"""\
<main-goal>
You are playing Diplomacy. Your goal is to win by controlling 18+ supply centres.
</main-goal>

<general-instructions>
* Choose legal DATC orders **only** for *your* power.
* You must occupy supply centers with a unit at end of Fall to capture them.
* A supply center must be empty in order to build a unit there.
    * (But be aware: empty supply centers are vulnerable to capture.)
* You may not build units in supply centers you do not own.
* You can only build units in your home supply centers.
* You may not necessarily own all of your home supply centers at a given time.
* If you do not own a particular home supply center, you cannot build units there.
* If you do not own a particular home supply center, it is probably important to recapture.

Respond with a JSON array of order strings - no commentary.
</general-instructions>

<power>
You are playing as {power}

Your home supply centers are: {home_centers}
</power>

<game-history>
This is the history of the game:

<order-history>
These are the orders submitted by each power in the last 2 phases:
{dump_dict(order_history)}

</order-history>
<result-history>
These are the no-convoy, bounces, voids, cuts, dislodged, disrupted, disbanded, and maybe results for each phase.

Successfully orders will not appear in this list.
{dump_dict(result_history)}


</result-history>
<state-history>
This is the history of the board state for each phase:
{dump_dict(state_history)}
</state-history>
</game-history>

<full-game-current-state>
This is the full game state for all powers:

all_supply_center_counts:
{dump_dict(engine.supply_center_counts)}

all_supply_centers:
{dump_dict(engine.supply_centers)}

all_units:
{dump_dict(engine.units)}

game_phase_type: {engine.phase_type}
game_year: {engine.year}
game_phase: {engine.phase}
game_short_phase: {engine.short_phase}
</full-game-current-state>

<your-current-state>
owned_supply_centers: {owned_centers}

units:
{dump_dict(engine.units[power])}

possible_moves:
{dump_dict(engine.possible_orders[power])}
</your-current-state>

<specific-instructions>
{guidance}
</specific-instructions>
"""

    # ------------------------------------------------------------------
    # Diagnostics – token length & oversized prompt handling
    # ------------------------------------------------------------------
    token_count = _count_tokens(prompt)
    logger.debug("Orders prompt length for %s/%s: %d tokens", engine.short_phase, power, token_count)

    if token_count > 4_096:
        _persist_long_prompt(prompt, engine.short_phase, power, token_count)

    # ------------------------------------------------------------------
    # Return
    # ------------------------------------------------------------------
    return prompt
