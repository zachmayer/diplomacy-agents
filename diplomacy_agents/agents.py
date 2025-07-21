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

# stdlib
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from time import perf_counter
from typing import Literal, TypeVar, cast

from pydantic_ai import Agent, NativeOutput, ToolOutput, models
from pydantic_ai.models import KnownModelName

from diplomacy_agents.engine import GameStateDTO, Orders, Power, PowerViewDTO
from diplomacy_agents.prompts import build_orders_prompt

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

    def __init__(self, power: Power) -> None:
        """Store the owning *power* token for later reference and initialise cost tracking."""
        self.power = power
        self.total_runtime_s: float = 0.0

        # Decide wrapper at subclass level; default to ToolOutput.
        self.output_wrapper = ToolOutput

        # Per-agent cumulative token buckets → {model: {bucket: count}}
        self.token_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    @abstractmethod
    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Return a list of DATC order strings for *power* in the current phase."""
        raise NotImplementedError  # pragma: no cover

    # BaseAgent no longer exposes a messaging API.


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
        for opts in _view.my_possible_orders_by_location.values():
            orders.append(random.choice(opts))
        return orders


# ---------------------------------------------------------------------------
# Generic output spec typing -------------------------------------------------
# ---------------------------------------------------------------------------


# ``OutputSpec[T]`` captures the allowed ways of specifying a result schema
# for *pydantic-ai* agents:
#   1. A plain Python type (e.g. ``str``) – meaning "return exactly this type".
#   2. A ``ToolOutput`` wrapper specifying a tool schema.
#   3. A ``NativeOutput`` wrapper requesting the model's native structured output.
T = TypeVar("T")
type OutputSpec[T] = type[T] | ToolOutput[T] | NativeOutput[T]


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


# OutboundPress removed – gunboat mode eliminates messaging entirely.


class LLMAgent(BaseAgent):
    """Thin wrapper around *pydantic-ai* for a single power."""

    def __init__(self, power: Power, model_name: KnownModelName) -> None:
        """Bind *power* to a concrete ``pydantic-ai`` backend model."""
        super().__init__(power)
        self.model_name = model_name

        # Choose NativeOutput when the target model advertises JSON-schema native support.
        model_obj = models.infer_model(self.model_name)
        if model_obj.profile.supports_json_schema_output:
            self.output_wrapper = NativeOutput
        else:
            self.output_wrapper = ToolOutput

    async def _run_llm(
        self,
        prompt: str,
        output_type: OutputSpec[T],
        system_prompt: str | None = None,
    ) -> T:
        """Execute *prompt* using ``pydantic-ai`` and track runtime/cost."""
        if system_prompt is None:
            system_prompt = f"You are playing diplomacy as {self.power}. Your goal is to win"

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

        model_totals = self.token_totals[self.model_name]
        model_totals["request_tokens"] = model_totals.get("request_tokens", 0) + (usage_obj.request_tokens or 0)
        model_totals["response_tokens"] = model_totals.get("response_tokens", 0) + (usage_obj.response_tokens or 0)

        # Provider-specific buckets live in `.details` when present.
        details: dict[str, int] | None = getattr(usage_obj, "details", None)
        if details:
            for k, v in details.items():
                model_totals[k] = model_totals.get(k, 0) + v

        return result.output

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Delegate order creation to the configured LLM via *pydantic-ai*."""
        # Build a Literal union of all allowed order strings, then ask for a list of these literals.
        orders_literal = Literal[tuple(_view.legal_orders_list)]  # type: ignore[misc]

        base_type = list[orders_literal]  # noqa: PTH123 (typing generic alias)

        output_type = self.output_wrapper(
            base_type,
            name="valid_orders",
            description="Return a list of valid orders for your power in the current phase.",
            strict=len(_view.legal_orders_list) <= 1000,
        )

        prompt = build_orders_prompt(_game_state, _view)

        orders = await self._run_llm(
            prompt=prompt,
            output_type=output_type,
        )

        return cast(Orders, orders)

    # Messaging support removed for gunboat mode – this agent now focuses solely on orders.
