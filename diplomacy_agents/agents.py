"""
Agents controlling each power – baseline (hold/random) and LLM‑backed.

The module is intentionally self‑contained so callers who need only baseline
agents do **not** import the heavier *pydantic‑ai* dependency chain.
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from collections import defaultdict
from time import perf_counter
from typing import Literal, TypeVar

from pydantic_ai import Agent, NativeOutput, ToolOutput, models
from pydantic_ai.models import KnownModelName

from diplomacy_agents.engine import GameStateDTO, Orders, PowerViewDTO
from diplomacy_agents.enums import Power
from diplomacy_agents.prompts import build_orders_prompt

logger = logging.getLogger(__name__)

__all__ = [
    "BaseAgent",
    "HoldAgent",
    "RandomAgent",
    "LLMAgent",
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

        # Subclasses may switch this to NativeOutput when the LLM supports JSON‑schema.
        self.output_wrapper = ToolOutput

        # Per‑model cumulative token buckets → {model_name: {bucket: count}}
        self.token_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # NOTE: Concrete subclasses must implement -----------------------------------------------------------------

    @abstractmethod
    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Return a tuple of DATC‑formatted order strings for *self.power* in thecurrent phase."""
        raise NotImplementedError  # pragma: no cover


# ---------------------------------------------------------------------------
# Baseline agents
# ---------------------------------------------------------------------------


class HoldAgent(BaseAgent):
    """Agent that issues no orders – every unit *holds* / *waits*."""

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Return an empty order set."""
        return ()  # type: Orders


class RandomAgent(BaseAgent):
    """Agent that submits **one random legal order** for each controllable unit in the current phase."""

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Pick exactly one random order per orderable location."""
        chosen = tuple(random.choice(opts) for opts in _view.possible_orders.values())
        return chosen  # type: Orders


# ---------------------------------------------------------------------------
# Generic output‑spec typing (for pydantic‑ai)
# ---------------------------------------------------------------------------

T = TypeVar("T")
type OutputSpec[T] = type[T] | ToolOutput[T] | NativeOutput[T]  # pyright: ignore[reportInvalidTypeForm]


# ---------------------------------------------------------------------------
# LLM‑backed agent
# ---------------------------------------------------------------------------


class LLMAgent(BaseAgent):
    """Thin wrapper around *pydantic‑ai* for a single power."""

    def __init__(self, power: Power, model_name: KnownModelName) -> None:
        """Bind *power* to a concrete backend model and choose the output wrapper."""
        super().__init__(power)
        self.model_name = model_name

        # Prefer NativeOutput when the target model advertises JSON‑schema support.
        # Otherwise use tool calls for JSON output via a tool call.
        if models.infer_model(model_name).profile.supports_json_schema_output:
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
        """Execute *prompt* via *pydantic‑ai*, accumulate runtime & token usage,and return the structured output produced by the model."""
        if system_prompt is None:
            system_prompt = f"You are playing Diplomacy as {self.power}. Your goal is to win."

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

        usage = result.usage()
        buckets = self.token_totals[self.model_name]
        buckets["request_tokens"] += usage.request_tokens or 0
        buckets["response_tokens"] += usage.response_tokens or 0
        if details := getattr(usage, "details", None):
            for k, v in details.items():
                buckets[k] += v

        return result.output

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    async def get_orders(self, _game_state: GameStateDTO, _view: PowerViewDTO) -> Orders:
        """Ask the configured LLM for a valid order set, constrained to the exactlist of legal options provided in *_view*."""
        # Build a Literal union over **all** legal order strings.
        # PEP 646's unpacking (`*tuple`) expands into individual literal args.
        orders_literal = Literal[*_view.flat_orders]  # type: ignore[misc, valid-type]

        # Request a *list* of those literals, then wrap it for pydantic‑ai.
        base_type = list[orders_literal]

        output_type = self.output_wrapper(
            base_type,
            name="valid_orders",
            description="Return a list of valid orders for your power in this phase.",
            strict=len(_view.flat_orders) <= 1_000,
        )

        prompt = build_orders_prompt(_game_state, _view)
        raw_orders = await self._run_llm(prompt=prompt, output_type=output_type)

        return tuple(str(order) for order in raw_orders)
