"""Asynchronous self-play driver orchestrating seven agents (LLMs or baselines)."""

from __future__ import annotations

import asyncio
import random
from typing import Any, cast

from pydantic_ai.models import KnownModelName

from diplomacy_agents.agents import HoldAgent, LLMAgent, RandomAgent
from diplomacy_agents.engine import AgentSpecName, DiplomacyEngine, Power, PowerModelMap, flatten_values

# Available LLM model identifiers considered for random assignment.
LOCAL_MODEL_NAMES: list[AgentSpecName] = [
    "openai:o3",
    "openai:o4-mini",
    "openai:gpt-4.1",
    "openai:gpt-4.1-mini",
    "openai:gpt-4.1-nano",
    "openai:gpt-4o",
    "anthropic:claude-opus-4-0",
    "anthropic:claude-sonnet-4-0",
    "google-gla:gemini-2.5-pro",
    "google-gla:gemini-2.5-flash",
    # Baseline agents --------------------------------------------------
    "hold",
    "random",
]

__all__ = ["GameOrchestrator", "run_game"]


# ---------------------------------------------------------------------------
# High-level orchestrator -----------------------------------------------------
# ---------------------------------------------------------------------------


class GameOrchestrator:
    """High-level game loop coordinating engine and agents."""

    def __init__(
        self,
        *,
        model_map: PowerModelMap | None = None,
        seed: int | None = None,
    ) -> None:
        """
        Initialise orchestrator and freeze *power* → *model* assignment.

        Parameters
        ----------
        model_map
            Explicit mapping from each of the seven powers to a concrete
            ``KnownModelName``.  When given the orchestrator will **not** pick
            models randomly.  The mapping must cover *exactly* the standard
            seven powers; otherwise a ``ValueError`` is raised.
        seed
            Optional random seed to make random assignments deterministic –
            useful for repeatable tests.

        """
        self.engine = DiplomacyEngine()

        if seed is not None:
            random.seed(seed)

        # Build or validate the power → spec mapping.
        if model_map is None:
            # Randomly assign an LLM model to each power.
            rnd_map_untyped = {p: random.choice(LOCAL_MODEL_NAMES) for p in self.engine.get_game_state().powers}
            rnd_map = cast(dict[str, AgentSpecName], rnd_map_untyped)
            self.model_map = PowerModelMap(**rnd_map)
        else:
            self.model_map = model_map

        # Freeze the assignment at instantiation time so subsequent phases keep
        # using the same underlying model for each power regardless of board
        # changes or eliminations.
        self.agents: dict[Power, Any] = self._init_agents()

    # ------------------------------------------------------------------
    # Main public API ---------------------------------------------------
    # ------------------------------------------------------------------

    async def run(self) -> dict[Power, int]:  # noqa: D401
        """Run the match to completion – returns final supply-centre counts."""
        while not self.engine.get_game_state().is_game_done:
            await self._run_single_phase()
        return self.engine.get_game_state().supply_centers

    # ------------------------------------------------------------------
    # Internals ---------------------------------------------------------
    # ------------------------------------------------------------------

    def _init_agents(self) -> dict[Power, Any]:
        """Create and return the immutable power → agent mapping."""
        state = self.engine.get_game_state()

        mapping = self.model_map.model_dump()
        agents: dict[Power, Any] = {}
        for p in state.powers:
            spec = cast(str, mapping[p])
            low = spec.lower()
            if low == "hold":
                agents[p] = HoldAgent(p)
            elif low == "random":
                agents[p] = RandomAgent(p)
            else:
                agents[p] = LLMAgent(p, cast(KnownModelName, spec))
        return agents

    async def _run_single_phase(self) -> None:
        # Build power-specific tasks only for powers that still own units.
        state = self.engine.get_game_state()

        tasks: dict[Power, asyncio.Task[list[str]]] = {}
        for power in state.powers:
            view = self.engine.get_power_view(power)
            if not flatten_values(view.orders_by_location):  # no units/orders
                continue  # eliminated powers – skip
            task = asyncio.create_task(self.agents[power].get_orders(state, view))
            tasks[power] = task

        if not tasks:  # all powers eliminated? – should be game over
            return

        results: list[list[str]] = await asyncio.gather(*tasks.values())
        for p, orders in zip(tasks.keys(), results, strict=False):
            self.engine.submit_orders(p, orders)

        self.engine.process_turn()


# Convenience wrapper --------------------------------------------------------


def run_game(
    *,
    model_map: PowerModelMap | None = None,
    seed: int | None = None,
) -> dict[Power, int]:  # noqa: D401
    """
    Blocking helper for synchronous callers (e.g. CLI).

    This thin wrapper mirrors ``GameOrchestrator``'s keyword parameters so it
    can be used interchangeably in simple scripts.
    """

    async def _runner() -> dict[Power, int]:
        orch = GameOrchestrator(model_map=model_map, seed=seed)
        return await orch.run()

    return asyncio.run(_runner())


# No BaseAgent import needed here.
