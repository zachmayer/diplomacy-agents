"""
Agents controlling each power - baseline (hold/random) and LLM-backed.

The module is intentionally self-contained so callers who need only baseline
agents do **not** import the heavier *pydantic-ai* dependency chain.
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from collections import defaultdict
from time import perf_counter
from typing import Annotated, TypeVar, override

from pydantic import GetPydanticSchema
from pydantic_ai import Agent, NativeOutput, ToolOutput, models
from pydantic_ai.models import KnownModelName
from pydantic_core import core_schema

from diplomacy_agents.engine import DiplomacyEngine, Orders
from diplomacy_agents.enums import Power
from diplomacy_agents.prompts import build_orders_prompt

logger = logging.getLogger(__name__)

__all__ = [
    "BaseAgent",
    "HoldAgent",
    "RandomAgent",
    "LLMAgent",
    "order_list_type",
]

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseAgent(ABC):
    """Common asynchronous interface shared by all power controllers."""

    def __init__(self, power: Power) -> None:
        """Store the *power* this agent controls and reset runtime / cost stats."""
        self.power = power
        self.total_runtime_s: float = 0.0

        # Subclasses may switch this to NativeOutput when the LLM supports JSON-schema.
        self.output_wrapper: type[ToolOutput[list[str]]] | type[NativeOutput[list[str]]] = ToolOutput

        # Per-model cumulative token buckets → {model_name: {bucket: count}}
        self.token_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    @abstractmethod
    async def get_orders(self, engine: DiplomacyEngine) -> Orders:
        """Return a tuple of DATC-formatted order strings for *self.power* in thecurrent phase."""
        raise NotImplementedError  # pragma: no cover


# ---------------------------------------------------------------------------
# Baseline agents
# ---------------------------------------------------------------------------


class HoldAgent(BaseAgent):
    """Agent that issues no orders - every unit *holds* / *waits*."""

    @override
    async def get_orders(self, engine: DiplomacyEngine) -> Orders:
        """Return an empty order set."""
        return ()


class RandomAgent(BaseAgent):
    """Agent that submits **one random legal order** for each controllable unit in the current phase."""

    @override
    async def get_orders(self, engine: DiplomacyEngine) -> Orders:
        """Pick exactly one random order per orderable location."""
        chosen = tuple(random.choice(opts) for opts in engine.possible_orders[self.power].values())
        return chosen


# ---------------------------------------------------------------------------
# Generic output-spec typing (for pydantic-ai)
# ---------------------------------------------------------------------------

T = TypeVar("T")
type OutputSpec[T] = type[T] | ToolOutput[T] | NativeOutput[T]


# ---------------------------------------------------------------------------
# Legal-order output type
# ---------------------------------------------------------------------------


def order_list_type(flat_orders: Orders, max_schema_size: int) -> type[list[str]]:
    """
    Return the output type for a list of orders, limited to *flat_orders* when that list is reasonably small.

    The legal set is only known at runtime, so the static type is ``list[str]``, and Pydantic gets the core schema
    it would build for ``Literal[*flat_orders]``: same JSON schema, same validation, same retry feedback. For
    extremely large lists we fall back to a plain ``str`` element type to avoid a gigantic literal schema.
    """
    if len(flat_orders) > max_schema_size:
        return list[str]

    # ``Literal[...]`` drops repeats, such as the ``WAIVE`` every build location offers.
    legal_orders = list(dict.fromkeys(flat_orders))
    return list[Annotated[str, GetPydanticSchema(lambda _source, _handler: core_schema.literal_schema(legal_orders))]]


# ---------------------------------------------------------------------------
# LLM-backed agent
# ---------------------------------------------------------------------------


class LLMAgent(BaseAgent):
    """Thin wrapper around *pydantic-ai* for a single power."""

    def __init__(self, power: Power, model_name: KnownModelName) -> None:
        """Bind *power* to a concrete backend model and choose the output wrapper."""
        super().__init__(power)
        self.model_name = model_name

        # Prefer NativeOutput when the target model advertises JSON-schema support.
        # Otherwise use tool calls for JSON output via a tool call.
        if models.infer_model(model_name).profile.get("supports_json_schema_output", False):
            self.output_wrapper = NativeOutput

    # ------------------------------------------------------------------ #
    # Private helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _run_llm(
        self,
        prompt: str,
        output_type: OutputSpec[T],
        system_prompt: str | None = None,
    ) -> T:
        """Execute *prompt* via *pydantic-ai*, accumulate runtime & token usage,and return the structured output produced by the model."""
        if system_prompt is None:
            system_prompt = f"You are playing Diplomacy as {self.power}. Your goal is to win."

        agent: Agent[None, T] = Agent(
            model=self.model_name,
            system_prompt=system_prompt,
            output_type=output_type,
            retries={"tools": 1, "output": 3},
        )

        start = perf_counter()
        result = await agent.run(prompt)
        self.total_runtime_s += perf_counter() - start

        usage = result.usage
        buckets = self.token_totals[self.model_name]
        buckets["request_tokens"] += usage.input_tokens
        buckets["response_tokens"] += usage.output_tokens
        if details := getattr(usage, "details", None):
            for k, v in details.items():
                buckets[k] += v

        return result.output

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    @override
    async def get_orders(self, engine: DiplomacyEngine, max_schema_size: int = 1_000) -> Orders:
        """Ask the configured LLM for a valid order set, constrained to the exact list of legal options provided in *engine*."""
        flat_orders = engine.flat_possible_orders[self.power]

        output_type = self.output_wrapper(
            order_list_type(flat_orders, max_schema_size),
            name="valid_orders",
            description="Return a list of valid orders for your power in this phase.",
            strict=len(flat_orders) <= max_schema_size,
        )

        prompt = build_orders_prompt(engine, self.power)
        raw_orders = await self._run_llm(prompt=prompt, output_type=output_type)

        return tuple(str(order) for order in raw_orders)
