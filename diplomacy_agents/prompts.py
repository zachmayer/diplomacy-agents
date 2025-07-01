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

    The output is intentionally **plain text** with lightweight XML-style
    section tags so that it remains readable while still being easy to parse
    or split if needed.

    The prompt contains four parts:

    1. A short *goal* reminding the model of the win condition.
    2. The current phase and the power the model is playing.
    3. A JSON dump of the complete public ``GameStateDTO``.
    4. A JSON dump of the requesting power's ``PowerViewDTO`` including the
       ``orders_by_location`` mapping which enumerates all legal DATC orders.

    Finally, it instructs the model to reply **only** with a JSON array of
    selected order strings.  The *pydantic-ai* wrapper validates the response
    against the schema returned by ``PowerViewDTO.create_order_model``.
    """
    game_state_json = json.dumps(game_state.model_dump(mode="json"), indent=2, sort_keys=True)
    view_json = json.dumps(view.model_dump(mode="json"), indent=2, sort_keys=True)

    prompt = (
        "<main-goal>\n"
        "You are playing Diplomacy, a strategy board game. Your objective is to win by controlling "
        "18 or more supply centres.\n"
        "</main-goal>\n\n"
        f"<who-am-i>\nYou are power {view.power} in phase {view.phase}.\n</who-am-i>\n\n"
        "<game-state>\n"
        f"{game_state_json}\n"
        "</game-state>\n\n"
        "<your-view>\n"
        f"{view_json}\n"
        "</your-view>\n\n"
        "<instructions>\n"
        "Choose exactly one legal DATC order for each of *your* units. "
        "Respond **only** with a JSON array of order strings (one per unit).\n"
        "</instructions>"
    )

    return prompt
