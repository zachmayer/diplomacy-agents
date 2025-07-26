"""Prompt-construction helpers for Diplomacy LLM agents."""

import json
from collections.abc import Callable, Mapping, Sized
from typing import TypeGuard, TypeVar

from diplomacy_agents.engine import DiplomacyEngine
from diplomacy_agents.enums import PhaseType, Power

# Public re-exports ----------------------------------------------------

__all__: list[str] = [
    "build_orders_prompt",
]

lost_home_center_note = """
Note that home supply centers are the only places you can build units.
You may not own some or all of your home supply centers.
If you do not own a particular home supply center, you cannot build units there.

If you do not own a particular home supply center, it is probably important to recapture.
"""

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


def build_orders_prompt(engine: DiplomacyEngine, power: "Power") -> str:
    """Return the full instruction prompt for orders generation."""
    guidance_fn = _PHASE_GUIDE.get(str(engine.phase_type), lambda _e, _p: "")
    guidance = guidance_fn(engine, power)

    home_centers = tuple(sorted(engine.home_supply_centers[power]))
    owned_centers = tuple(sorted(engine.supply_centers[power]))

    write_lost_home_center_note = len(set(home_centers) - set(owned_centers)) > 0

    return f"""\
<main-goal>
You are playing Diplomacy. Your goal is to win by controlling 18+ supply centres.
</main-goal>

<power>
You are playing as {power}
</power>

<general-instructions>
* Choose legal DATC orders **only** for *your* power.
* You must occupy supply centers with a unit at end of Fall to capture them.
* A supply center must be empty in order to build a unit there.
    * (But be aware: Empty supply centers are vulnerable to capture.)
* You may not build units in supply centers you do not own.

Respond with a JSON array of order strings - no commentary.
</general-instructions>

<game-history>
This is the history of the game:

<order-history>
These are the orders submitted by each power in each phase:
{dump_dict(engine.order_history)}

</order-history>
<result-history>
These are the results of the orders for each phase:
{dump_dict(engine.result_history)}

</result-history>
<state-history>
This is the history of the board state for each phase:
{dump_dict(engine.state_history)}
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

<you>
These are your power, owned supply centers and home supply centers

- power: {power}
- owned_supply_centers: {owned_centers}
- home_supply_centers: {home_centers}
{lost_home_center_note if write_lost_home_center_note else ""}
These are your units and possible moves:

units:
{dump_dict(engine.units[power])}

possible_moves:
{dump_dict(engine.possible_orders[power])}
</you>

<specific-instructions>
{guidance}
</specific-instructions>
"""
