"""Asynchronous self-play driver for seven AI powers."""

from __future__ import annotations

import asyncio
import random
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

from diplomacy_agents.engine import DiplomacyEngine, GameStateDTO, Power, PowerViewDTO
from diplomacy_agents.literals import MODEL_NAMES  # candidate model list
from diplomacy_agents.prompts import build_orders_prompt

__all__ = ["GameOrchestrator", "run_game"]


class OrderAgent:
    """Thin wrapper around *pydantic-ai* for a single power."""

    def __init__(self, power: Power, model_name: KnownModelName) -> None:
        self.power = power
        self.model_name = model_name

    async def get_orders(self, game_state: GameStateDTO, view: PowerViewDTO) -> list[str]:  # noqa: D401
        """Request one order per unit from the underlying LLM."""
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

        # Cast the output to the proper RootModel subclass so the type checker
        # recognises the "root" attribute. This avoids pyright's unknown-attribute
        # diagnostics while still keeping the runtime lookup straightforward.
        from pydantic import RootModel  # local import to prevent global dependency

        data = cast(RootModel[list[str]], result.output)

        return list(data.root)


class GameOrchestrator:
    """High-level game loop coordinating engine and agents."""

    def __init__(self, model_pool: tuple[KnownModelName, ...] | None = None, *, seed: int | None = None) -> None:
        """Initialise orchestrator and assign random models."""
        self.engine = DiplomacyEngine()
        if seed is not None:
            random.seed(seed)

        self.model_pool: tuple[KnownModelName, ...] = model_pool or MODEL_NAMES
        self.agents: dict[Power, OrderAgent] = self._init_agents()

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

    def _init_agents(self) -> dict[Power, OrderAgent]:
        state = self.engine.get_game_state()
        return {p: OrderAgent(p, random.choice(self.model_pool)) for p in state.powers}

    async def _run_single_phase(self) -> None:
        # Build power-specific tasks only for powers that still own units.
        state = self.engine.get_game_state()

        tasks: dict[Power, asyncio.Task[list[str]]] = {}
        for power in state.powers:
            view = self.engine.get_power_view(power)
            if not view.units:
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


def run_game(seed: int | None = None) -> dict[Power, int]:  # noqa: D401
    """Blocking helper for synchronous callers (e.g. CLI)."""

    async def _runner() -> dict[Power, int]:
        orch = GameOrchestrator(seed=seed)
        return await orch.run()

    return asyncio.run(_runner())
