"""Asynchronous self-play driver orchestrating seven agents (LLMs or baselines)."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

from pydantic_ai.models import KnownModelName

from diplomacy_agents.agents import BaseAgent, HoldAgent, LLMAgent, RandomAgent
from diplomacy_agents.engine import DiplomacyEngine, Orders, Power

AgentSpecName = KnownModelName | Literal["hold", "random"]


class PowerModelMap(dict[Power, AgentSpecName]):
    """Mapping from each power to its agent specification."""

    ENGLAND: AgentSpecName
    FRANCE: AgentSpecName
    GERMANY: AgentSpecName
    ITALY: AgentSpecName
    RUSSIA: AgentSpecName
    TURKEY: AgentSpecName
    AUSTRIA: AgentSpecName


LOCAL_MODEL_NAMES: list[AgentSpecName] = [
    # "openai:o3",
    # "openai:o4-mini",
    "openai:gpt-4.1",
    "openai:gpt-4.1-mini",
    "openai:gpt-4.1-nano",
    # "openai:gpt-4o",
    # "anthropic:claude-opus-4-0",
    # "anthropic:claude-sonnet-4-0",
    # "google-gla:gemini-2.5-pro",
    "google-gla:gemini-2.5-flash",
    # Baseline agents --------------------------------------------------
    "hold",
    "random",
]

__all__ = ["GameOrchestrator", "run_game", "PowerModelMap"]


# ---------------------------------------------------------------------------
# Module-level logger --------------------------------------------------------
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


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
            self.model_map: PowerModelMap = PowerModelMap(
                {
                    "ENGLAND": random.choice(LOCAL_MODEL_NAMES),
                    "FRANCE": random.choice(LOCAL_MODEL_NAMES),
                    "GERMANY": random.choice(LOCAL_MODEL_NAMES),
                    "ITALY": random.choice(LOCAL_MODEL_NAMES),
                    "RUSSIA": random.choice(LOCAL_MODEL_NAMES),
                    "TURKEY": random.choice(LOCAL_MODEL_NAMES),
                    "AUSTRIA": random.choice(LOCAL_MODEL_NAMES),
                }
            )
        else:
            self.model_map = model_map

        # Log the frozen power assignments at game start for easier debugging.
        logger.info("Initial: %s", self.model_map)

        # Freeze the assignment at instantiation time so subsequent phases keep
        # using the same underlying model for each power regardless of board
        # changes or eliminations.
        self.agents: dict[Power, BaseAgent] = self._init_agents()

    # ------------------------------------------------------------------
    # Main public API ---------------------------------------------------
    # ------------------------------------------------------------------

    async def run(self) -> dict[Power, int]:
        """Run the match to completion – returns final supply-centre counts."""
        while not self.engine.get_game_state().is_game_done:
            await self._run_single_phase()

        # Capture final board state after the game concludes.
        self.engine.capture_frame()

        # Persist full game data and board animation.
        self.engine.save("game_saves/game_state.datc")
        self.engine.save_animation("board_svg/board_animation.svg")

        return self.engine.get_game_state().all_supply_center_counts

    # ------------------------------------------------------------------
    # Internals ---------------------------------------------------------
    # ------------------------------------------------------------------

    def _init_agents(self) -> dict[Power, BaseAgent]:
        """Create and return the immutable power → agent mapping."""
        state = self.engine.get_game_state()

        agents: dict[Power, BaseAgent] = {}
        for p in state.all_powers:
            spec = self.model_map[p]
            if spec == "hold":
                agents[p] = HoldAgent(p)
            elif spec == "random":
                agents[p] = RandomAgent(p)
            else:
                agents[p] = LLMAgent(p, spec)
        return agents

    async def _run_single_phase(self) -> None:
        # The engine now records frames internally; capturing happens there.

        # Log current supply-centre distribution for easier debugging/analysis.
        state = self.engine.get_game_state()
        logger.info("Phase %s: %s", state.phase, state.all_supply_center_counts)

        # Build power-specific tasks only for powers that still own units.
        tasks: dict[Power, asyncio.Task[Orders]] = {}
        for power in state.all_powers:
            view = self.engine.get_power_view(power)
            if not view.orders_list:  # no units/orders
                continue  # eliminated powers – skip
            task = asyncio.create_task(self.agents[power].get_orders(state, view))
            tasks[power] = task

        if not tasks:  # all powers eliminated? – should be game over
            return

        await asyncio.gather(*tasks.values())
        for power, task in tasks.items():
            self.engine.submit_orders(power, task.result())

        self.engine.process_turn()


# Convenience wrapper --------------------------------------------------------


def run_game(
    *,
    model_map: PowerModelMap | None = None,
    seed: int | None = None,
) -> dict[Power, int]:
    """
    Blocking helper for synchronous callers (e.g. CLI).

    This thin wrapper mirrors ``GameOrchestrator``'s keyword parameters so it
    can be used interchangeably in simple scripts.
    """

    async def _runner() -> dict[Power, int]:
        orch = GameOrchestrator(model_map=model_map, seed=seed)
        return await orch.run()

    return asyncio.run(_runner())
