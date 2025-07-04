"""
Prompt construction helpers.

Currently only implements a simple builder for the *orders* task.  It embeds a
JSON serialisation of both the global ``GameStateDTO`` and the power-specific
``PowerViewDTO`` so that the language model has full context as well as the
legal orders it may choose from.
"""

from __future__ import annotations

import json

from diplomacy_agents.engine import GameStateDTO, PowerViewDTO

__all__: list[str] = ["build_orders_prompt"]


# ---------------------------------------------------------------------------
# Orders prompt --------------------------------------------------------------
# ---------------------------------------------------------------------------


def build_orders_prompt(game_state: GameStateDTO, view: PowerViewDTO) -> str:  # noqa: D401
    """
    Return an instruction prompt for the *orders* agent.

    The prompt contains four parts:

    1. A short *goal* reminding the model of the win condition.
    2. The current phase and the power the model is playing.
    3. A JSON dump of the complete public ``GameStateDTO``.
    4. A JSON dump of the requesting power's ``PowerViewDTO`` including the
       ``orders_by_location`` mapping which enumerates all legal DATC orders.
    """
    game_state_json = json.dumps(game_state.model_dump(mode="json"), indent=2, sort_keys=False)
    view_json = json.dumps(view.model_dump(mode="json"), indent=2, sort_keys=False)

    # ------------------------------------------------------------------
    # Dynamic phase-specific guidance -----------------------------------
    # ------------------------------------------------------------------
    extra_guidance: list[str] = []

    if game_state.phase_type == "A":  # Adjustment – builds or disbands
        diff = view.my_supply_center_count - len(view.my_unit_locations)
        if diff > 0:
            extra_guidance.append(f"\nYou have {diff} build(s). Return an array of exactly {diff} DATC build order(s).")
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
        pending_units = len(view.my_orders_by_location)
        if pending_units > 0:
            extra_guidance.append(
                f"\nYou have {pending_units} dislodged unit(s)."
                f"\nReturn an array of exactly {pending_units} DATC retreat or disband order(s)."
                f"\nYou must submit exactly one order per dislodged unit."
            )

    guidance_block = "\n".join(extra_guidance)

    prompt = f"""
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

<instructions>
Choose legal DATC orders. Respond **only** with a JSON array of order strings.{guidance_block}
</instructions>"""

    return prompt
