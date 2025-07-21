"""Prompt construction helpers."""

from __future__ import annotations

import json

from diplomacy_agents.engine import GameStateDTO, PowerViewDTO

__all__: list[str] = ["build_orders_prompt"]


def _build_common_prompt(game_state: GameStateDTO, view: PowerViewDTO) -> str:  # noqa: D401
    """Return the common context block used by both orders and press prompts."""
    # Convert to plain dict so we can annotate *your* power keys with a suffix.
    game_state_dict = game_state.model_dump(mode="json")

    # Append " (YOU)" to the requesting power's keys in the board‐wide mappings.
    for field in [
        "all_supply_center_counts",
        "all_supply_center_locations",
        "all_unit_locations",
    ]:
        if field in game_state_dict and view.power in game_state_dict[field]:
            mapping = game_state_dict[field]
            mapping[f"{view.power} (YOU)"] = mapping.pop(view.power)

    # Remove redundant info not needed for language model context.
    game_state_dict.pop("all_powers", None)

    game_state_json = json.dumps(game_state_dict, indent=2, sort_keys=False)
    # The ``press_messages`` list may contain non-JSON-serialisable objects,
    # but ``model_dump_json`` handles them via Pydantic's default encoders.
    view_json = view.model_dump_json(indent=2)

    return f"""
<main-goal>
You are playing Diplomacy, a strategy board game. Your objective is to win by controlling 18 or more supply centres.
</main-goal>

<who-am-i>
You are power {view.power} in phase {game_state.phase_long} ({game_state.phase}).
</who-am-i>

<full-game-state>
{game_state_json}
</full-game-state>

<your-power-view>
{view_json}
</your-power-view>

<your-possible-legal-orders>
{view.legal_orders_list}
</your-possible-legal-orders>
"""


def build_orders_prompt(game_state: GameStateDTO, view: PowerViewDTO) -> str:
    """Return an instruction prompt for the *orders* agent."""
    prompt = _build_common_prompt(game_state, view)

    # ------------------------------------------------------------------
    # Dynamic phase-specific guidance -----------------------------------
    # ------------------------------------------------------------------
    extra_guidance: list[str] = []

    if game_state.phase_type == "A":  # Adjustment – builds or disbands
        diff = view.my_supply_center_count - len(view.my_unit_locations)
        if diff > 0:
            extra_guidance.append(
                f"\nYou have {diff} build(s)."
                f"\nReturn an array **of exactly {diff} DATC build order(s)**."
                "\n• Each build must occur in a *distinct* vacant home supply centre."
                "\n• Do **not** specify more than one build in the same location."
                "\n• Example (two builds): ['F BRE B', 'A PAR B']"
            )
        elif diff < 0:
            extra_guidance.append(
                f"\nYou must remove {-diff} unit(s). Return an array of exactly {-diff} DATC disband order(s)."
            )
    elif game_state.phase_type == "M":  # Movement – support / convoy note
        extra_guidance.append(
            "\nReturn an array of DATC order(s) for each of *your* units."
            "\nUnits without orders will hold."
            "\nYou may support or convoy other powers' units, but first consider your strategic goals."
        )
    elif game_state.phase_type == "R":
        pending_units = len(view.my_possible_orders_by_location)
        if pending_units > 0:
            extra_guidance.append(
                f"\nYou have {pending_units} dislodged unit(s)."
                f"\nReturn an array of exactly {pending_units} DATC retreat or disband order(s)."
                f"\nYou must submit exactly one order per dislodged unit."
            )

    guidance_block = "\n".join(extra_guidance)

    prompt = (
        f"\n\n<instructions>\nChoose legal DATC orders. Respond **only** with a JSON array of order strings.{guidance_block}\n</instructions>"
        + prompt
    )

    return prompt


# build_message_prompt has been removed – public press is no longer supported in gunboat mode.
