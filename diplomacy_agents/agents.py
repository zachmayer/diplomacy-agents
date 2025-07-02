from __future__ import annotations

# ruff: noqa: D100

"""Agents controlling each power – baseline (hold/random) and LLM-backed.

This module is purposely self-contained so the orchestrator can import
``make_agent`` without pulling in the heavy *pydantic-ai* dependency when the
caller only needs baseline agents.
"""

import random  # noqa: E402 – allowed after __future__ import
from abc import ABC, abstractmethod  # noqa: E402
from typing import cast  # noqa: E402

from pydantic import RootModel  # noqa: E402
from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models import KnownModelName  # noqa: E402

from diplomacy_agents.engine import GameStateDTO, Power, PowerViewDTO  # noqa: E402
from diplomacy_agents.prompts import build_orders_prompt  # noqa: E402

__all__ = [
    "BaseAgent",
    "HoldAgent",
    "RandomAgent",
    "LLMAgent",
]


# ---------------------------------------------------------------------------
# Abstract base --------------------------------------------------------------
# ---------------------------------------------------------------------------


class BaseAgent(ABC):
    """Common async interface shared by all power controllers."""

    def __init__(self, power: Power) -> None:  # noqa: D401
        """Store the owning *power* token for later reference."""
        self.power = power

    @abstractmethod
    async def get_orders(self, game_state: GameStateDTO, view: PowerViewDTO) -> list[str]:  # noqa: D401,ARG002
        """Return a list of DATC order strings for *power* in the current phase."""
        raise NotImplementedError  # pragma: no cover


# ---------------------------------------------------------------------------
# Baseline agents ------------------------------------------------------------
# ---------------------------------------------------------------------------


class HoldAgent(BaseAgent):
    """Agent that issues no orders (all units hold/wait)."""

    async def get_orders(self, game_state: GameStateDTO, view: PowerViewDTO) -> list[str]:  # noqa: D401,ARG002
        """Return an empty order list – interpreted as all units *hold*."""
        return []


class RandomAgent(BaseAgent):
    """Agent that submits one random legal order per controllable unit."""

    async def get_orders(self, game_state: GameStateDTO, view: PowerViewDTO) -> list[str]:  # noqa: D401,ARG002
        """Pick **one** random legal order per controlled unit."""
        orders: list[str] = []
        for opts in view.orders_by_location.values():
            if opts:  # skip empty tuples (rare but possible)
                orders.append(random.choice(opts))
        return orders


# ---------------------------------------------------------------------------
# LLM-backed agent -----------------------------------------------------------
# ---------------------------------------------------------------------------


class LLMAgent(BaseAgent):
    """Thin wrapper around *pydantic-ai* for a single power."""

    def __init__(self, power: Power, model_name: KnownModelName) -> None:
        """Bind *power* to a concrete ``pydantic-ai`` backend model."""
        super().__init__(power)
        self.model_name = model_name

    async def get_orders(self, game_state: GameStateDTO, view: PowerViewDTO) -> list[str]:  # noqa: D401,ARG002
        """Delegate order creation to the configured LLM via *pydantic-ai*."""
        order_model = view.create_order_model()

        agent = Agent(
            model=self.model_name,
            system_prompt=f"You are playing diplomacy as {self.power}.",
            output_type=order_model,
            retries=1,
            model_settings={"temperature": 0.7},
        )

        prompt = build_orders_prompt(game_state, view)
        result = await agent.run(prompt)

        data = cast(RootModel[list[str]], result.output)
        return list(data.root)
