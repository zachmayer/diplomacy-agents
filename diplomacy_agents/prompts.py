"""Prompt‑construction helpers for Diplomacy LLM agents."""

from __future__ import annotations

import json
from collections.abc import Callable

from diplomacy_agents.engine import GameStateDTO, PhaseType, PowerViewDTO

__all__ = ["build_orders_prompt"]


def _adjustment_guidance(view: PowerViewDTO) -> str:
    """Guidance for Adjustment (build / disband) phases."""
    diff = view.supply_center_count - len(view.units)
    if diff > 0:
        return (
            f"You have **{diff} build(s)**. Return exactly {diff} distinct build orders (e.g. ['F BRE B', 'A PAR B'])."
        )
    if diff < 0:
        removes = -diff
        return f"You must **disband {removes} unit(s)**. Return exactly {removes} disband order(s)."
    return "No builds or removals required; return an empty list."


def _movement_guidance(_: PowerViewDTO) -> str:
    """Guidance for Movement phases."""
    return "Issue one legal order to each of your units. Units without orders will *hold*."


def _retreat_guidance(view: PowerViewDTO) -> str:
    """Guidance for Retreat phases."""
    pending = len(view.possible_orders)
    return f"Each of your **{pending} dislodged unit(s)** needs exactly one retreat **or** disband order."


# Map phase‑code → guidance generator (functions take *view* only)
_PHASE_GUIDE: dict[str, Callable[[PowerViewDTO], str]] = {
    PhaseType.MOVEMENT: _movement_guidance,
    PhaseType.RETREAT: _retreat_guidance,
    PhaseType.ADJUSTMENT: _adjustment_guidance,
}


def build_orders_prompt(state: GameStateDTO, view: PowerViewDTO) -> str:
    """Return the full instruction prompt for orders generation."""
    guidance_fn = _PHASE_GUIDE.get(str(state.phase_type), lambda _v: "")
    guidance = guidance_fn(view)

    # ----- JSON snapshots --------------------------------------------------
    state_dict = state.model_dump(mode="json")
    for key in ("supply_center_counts", "supply_centers", "units"):
        if key in state_dict:
            mapping = state_dict[key]
            if view.power in mapping:
                mapping[f"{view.power.value} (YOU)"] = mapping.pop(view.power.value)
    state_dict.pop("powers", None)

    game_state_json = json.dumps(state_dict, indent=2)
    view_json = view.model_dump_json(indent=2)
    legal_orders = list(view.flat_orders)

    # ----- Final template --------------------------------------------------
    return f"""\
<main-goal>
You are playing Diplomacy. Win by owning 18+ supply centres.
</main-goal>

<instructions>
Choose legal DATC orders **only** for *your* power.
Respond with a JSON array of order strings - no commentary.
{guidance}
</instructions>

<full-game-state>
{game_state_json}
</full-game-state>

<your-power-view>
{view_json}
</your-power-view>

<your-possible-legal-orders>
{legal_orders}
</your-possible-legal-orders>
"""
