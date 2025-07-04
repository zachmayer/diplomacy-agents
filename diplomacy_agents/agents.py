"""
Agents controlling each power - baseline (hold/random) and LLM-backed.

This module is purposely self-contained so the orchestrator can import
``make_agent`` without pulling in the heavy *pydantic-ai* dependency when the
caller only needs baseline agents.
"""

from __future__ import annotations

import logging
import random
import re
from abc import ABC, abstractmethod
from enum import Enum
from time import perf_counter
from typing import Any, cast

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models import KnownModelName
from tokonomics import calculate_pydantic_cost

from diplomacy_agents.engine import GameStateDTO, Orders, Power, PowerViewDTO
from diplomacy_agents.prompts import build_orders_prompt, build_press_message_prompt

logger = logging.getLogger(__name__)


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

    # All agents carry an evolving public‐press history attached by the orchestrator.
    press_history: list[str]

    def __init__(self, power: Power) -> None:
        """Store the owning *power* token for later reference and initialise cost tracking."""
        self.power = power
        self.total_cost_usd: float = 0.0
        self.total_runtime_s: float = 0.0

        # Initialise empty press history – orchestrator will mutate this list.
        self.press_history = []

    @abstractmethod
    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Return a list of DATC order strings for *power* in the current phase."""
        raise NotImplementedError  # pragma: no cover

    # ------------------------------------------------------------------
    # Public press ------------------------------------------------------
    # ------------------------------------------------------------------

    async def get_press_message(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> str:  # noqa: D401
        """
        Return a public-press message or an empty string when saying nothing.

        Baseline agents simply remain silent by default.  LLM-backed agents
        override this method to generate public messages.
        """
        return ""


# ---------------------------------------------------------------------------
# Baseline agents ------------------------------------------------------------
# ---------------------------------------------------------------------------


class HoldAgent(BaseAgent):
    """Agent that issues no orders (all units hold/wait)."""

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Return an empty order list: all units hold."""
        return []


class RandomAgent(BaseAgent):
    """Agent that submits one random legal order per controllable unit."""

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Pick **one** random legal order per controlled unit."""
        orders: Orders = []
        for opts in _view.my_orders_by_location.values():
            orders.append(random.choice(opts))
        return orders


# ---------------------------------------------------------------------------
# LLM-backed agent -----------------------------------------------------------
# ---------------------------------------------------------------------------


def create_dynamic_enum_model(allowed_values: Orders) -> type[Enum]:
    """
    Build an Enum whose *values* are the exact order strings we pass in.

    The member *names* must be valid Python identifiers, so we derive them from
    the orders (or you could use "ORDER_1", "ORDER_2", …).
    """

    def safe_name(s: str) -> str:
        # Turn "A PAR - BUR" → "A_PAR_BUR"  (only letters, digits or _)
        return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_")

    members = {safe_name(v): v for v in allowed_values}

    # Enum(<name>, <members-dict>) returns a *new* Enum subclass
    return Enum("ValidOrders", members)


class LLMAgent(BaseAgent):
    """Thin wrapper around *pydantic-ai* for a single power."""

    def __init__(self, power: Power, model_name: KnownModelName) -> None:
        """Bind *power* to a concrete ``pydantic-ai`` backend model."""
        super().__init__(power)
        self.model_name = model_name

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Delegate order creation to the configured LLM via *pydantic-ai*."""
        allowed_orders = create_dynamic_enum_model(_view.orders_list)

        agent = Agent(
            model=self.model_name,
            system_prompt=f"You are playing diplomacy as {self.power}.",
            output_type=NativeOutput(
                list[allowed_orders],
                name="valid_orders",
                description="Return a list of valid orders for your power in the current phase.",
                strict=len(allowed_orders) <= 500,
            ),
            retries=1,
            output_retries=3,
        )

        prompt = build_orders_prompt(_game_state, _view)

        start = perf_counter()
        result = await agent.run(prompt)
        self.total_runtime_s += perf_counter() - start

        usage_obj = result.usage()
        cost = cast(Any, await calculate_pydantic_cost(self.model_name, usage_obj))  # type: ignore[call-arg]
        self.total_cost_usd += float(cost.total_cost)

        # Convert Enum members back to their underlying order strings
        return [o.value for o in result.output]

    # ------------------------------------------------------------------
    # Press message generation -----------------------------------------
    # ------------------------------------------------------------------

    async def get_press_message(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> str:  # noqa: D401
        """Generate a single concise public-press statement (or "" to remain silent)."""
        # Build the instruction prompt via reusable helper.
        prompt = build_press_message_prompt(_game_state, _view)

        # pydantic-ai agent returning a simple string.
        agent = Agent(
            model=self.model_name,
            system_prompt=f"You are playing diplomacy as {self.power}. Your goal is to win.",
            output_type=str,
            retries=1,
            output_retries=3,
        )

        start = perf_counter()
        result = await agent.run(prompt)
        self.total_runtime_s += perf_counter() - start

        usage_obj = result.usage()
        cost = cast(Any, await calculate_pydantic_cost(self.model_name, usage_obj))  # type: ignore[call-arg]
        self.total_cost_usd += float(cost.total_cost)

        # Normalise – ensure we return a plain string.
        message = str(result.output).strip()
        logger.info(f"{self.power} press message: {message}")
        return message
