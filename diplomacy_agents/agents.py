"""
Agents controlling each power - baseline (hold/random) and LLM-backed.

This module is purposely self-contained so the orchestrator can import
``make_agent`` without pulling in the heavy *pydantic-ai* dependency when the
caller only needs baseline agents.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

from diplomacy_agents.engine import GameStateDTO, Orders, Power, PowerViewDTO
from diplomacy_agents.prompts import build_orders_prompt

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

    def __init__(self, power: Power) -> None:
        """Store the owning *power* token for later reference."""
        self.power = power

    @abstractmethod
    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Return a list of DATC order strings for *power* in the current phase."""
        raise NotImplementedError  # pragma: no cover


# ---------------------------------------------------------------------------
# Baseline agents ------------------------------------------------------------
# ---------------------------------------------------------------------------


class HoldAgent(BaseAgent):
    """Agent that issues no orders (all units hold/wait)."""

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Return an empty order list – interpreted as all units *hold*."""
        return Orders([])


class RandomAgent(BaseAgent):
    """Agent that submits one random legal order per controllable unit."""

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Pick **one** random legal order per controlled unit."""
        orders: Orders = Orders([])
        for opts in _view.orders_by_location.values():
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

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Delegate order creation to the configured LLM via *pydantic-ai*."""
        order_model = _view.create_order_model()

        agent = Agent(
            model=self.model_name,
            system_prompt=f"You are playing diplomacy as {self.power}.",
            output_type=order_model,
            retries=1,
            output_retries=3,
        )

        prompt = build_orders_prompt(_game_state, _view)
        result = await agent.run(prompt)

        return cast(Orders, result.output)
