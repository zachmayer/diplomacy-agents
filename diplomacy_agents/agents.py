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
from datetime import datetime
from enum import Enum
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models import KnownModelName
from tokonomics import TokenCosts, calculate_pydantic_cost

from diplomacy_agents.engine import GameStateDTO, Orders, Power, PowerViewDTO
from diplomacy_agents.prompts import build_message_prompt, build_orders_prompt

logger = logging.getLogger(__name__)


__all__ = [
    "BaseAgent",
    "HoldAgent",
    "RandomAgent",
    "LLMAgent",
    "OutboundPress",
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
    # Unified messaging API -------------------------------------------
    # ------------------------------------------------------------------

    async def get_messages(
        self,
        _game_state: GameStateDTO,
        _view: PowerViewDTO,
        *,
        rounds_left: int,
    ) -> OutboundPress:  # noqa: D401
        """
        Return structured outbound press; default implementation sends nothing.

        The base implementation ignores *rounds_left* and simply returns an
        empty ``OutboundPress`` container so that non-LLM agents remain
        compatible without extra work.
        """
        _ = rounds_left  # deliberately unused to silence linters
        return OutboundPress()


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
# Generic output spec typing -------------------------------------------------
# ---------------------------------------------------------------------------


# ``OutputSpec[T]`` captures the two allowed ways of specifying a result schema
# for *pydantic-ai* agents:
#   1. A plain Python type (e.g. ``str``) – meaning "return exactly this type".
#   2. A ``NativeOutput`` wrapper with an explicit schema (e.g. a list of
#      dynamic order Enums).
T = TypeVar("T")
type OutputSpec[T] = type[T] | NativeOutput[T]


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


# ---------------------------------------------------------------------------
# Structured outbound press model -------------------------------------------
# ---------------------------------------------------------------------------


class OutboundPress(BaseModel):
    """
    Public and private messages for one press round.

    Each field is optional.  Omitted fields == no message to that recipient.

    Note that you can message yourself as a way to take notes or make plans,
    by using your own power name as the recipient.

    Keys:
    ALL      - broadcast visible to every power.
    <POWER>  - one of the seven standard power names for private 1→1 mail.
    """

    ALL: str | None = Field(default=None, description="Public broadcast visible to everyone.")

    ENGLAND: str | None = Field(default=None, description="Private message to ENGLAND.")
    FRANCE: str | None = Field(default=None, description="Private message to FRANCE.")
    GERMANY: str | None = Field(default=None, description="Private message to GERMANY.")
    ITALY: str | None = Field(default=None, description="Private message to ITALY.")
    RUSSIA: str | None = Field(default=None, description="Private message to RUSSIA.")
    TURKEY: str | None = Field(default=None, description="Private message to TURKEY.")
    AUSTRIA: str | None = Field(default=None, description="Private message to AUSTRIA.")

    model_config = ConfigDict(extra="forbid")


class LLMAgent(BaseAgent):
    """Thin wrapper around *pydantic-ai* for a single power."""

    def __init__(self, power: Power, model_name: KnownModelName) -> None:
        """Bind *power* to a concrete ``pydantic-ai`` backend model."""
        super().__init__(power)
        self.model_name = model_name

    async def _run_llm(
        self,
        prompt: str,
        output_type: OutputSpec[T],
        system_prompt: str | None = None,
    ) -> T:
        """Execute *prompt* using ``pydantic-ai`` and track runtime/cost."""
        if system_prompt is None:
            system_prompt = f"You are playing diplomacy as {self.power}. Your goal is to win."

        agent = Agent(
            model=self.model_name,
            system_prompt=system_prompt,
            output_type=output_type,
            retries=1,
            output_retries=3,
        )

        start = perf_counter()
        result = await agent.run(prompt)
        self.total_runtime_s += perf_counter() - start

        usage_obj = result.usage()
        cost: TokenCosts | None = await calculate_pydantic_cost(self.model_name, usage_obj)

        if cost is not None and cost.total_cost > 0.10:
            logger.warning(f"{self.power} llm call cost: {cost.total_cost}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Persist both the prompt and the raw model output for later inspection.
            prompt_path = f"debug/{self.power}_{timestamp}_prompt.txt"
            output_path = f"debug/{self.power}_{timestamp}_output.txt"
            with open(prompt_path, "w") as f_prompt:
                f_prompt.write(prompt)
            with open(output_path, "w") as f_output:
                f_output.write(str(result.output))

        if cost is not None:
            self.total_cost_usd += float(cost.total_cost)

        return result.output

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Delegate order creation to the configured LLM via *pydantic-ai*."""
        allowed_orders = create_dynamic_enum_model(_view.orders_list)

        output_type = NativeOutput(
            list[allowed_orders],
            name="valid_orders",
            description="Return a list of valid orders for your power in the current phase.",
            strict=len(allowed_orders) <= 500,
        )

        prompt = build_orders_prompt(_game_state, _view)

        raw_orders = await self._run_llm(
            prompt=prompt,
            output_type=output_type,
        )

        # Convert Enum members back to their underlying order strings
        return [o.value for o in raw_orders]

    # ------------------------------------------------------------------
    # Messaging generation ---------------------------------------------
    # ------------------------------------------------------------------

    async def get_messages(
        self,
        _game_state: GameStateDTO,
        _view: PowerViewDTO,
        *,
        rounds_left: int,
    ) -> OutboundPress:
        """
        Generate public/private messages as a structured ``OutboundPress`` model.

        The optional ``rounds_left`` hint lets the orchestrator inform the LLM
        how many messaging volleys remain in the current movement phase.  When
        of no interest to the implementation here beyond injecting it into the
        prompt.
        """
        prompt = build_message_prompt(_game_state, _view, rounds_left)

        messages: OutboundPress = await self._run_llm(
            prompt=prompt,
            output_type=OutboundPress,
        )

        return messages
