"""Asynchronous self-play driver orchestrating seven agents (LLMs or baselines)."""

from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
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

        # Store the seed and derive a shared filename suffix for reproducibility.
        self.seed = seed
        self._file_suffix = f"_{seed}" if seed is not None else ""

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

        # Running tally of USD cost per power.
        self._cost_usd_by_power: dict[Power, float] = defaultdict(float)

        # Running tally of LLM runtime (seconds) per power.
        self._runtime_s_by_power: dict[Power, float] = defaultdict(float)

    # ------------------------------------------------------------------
    # Main public API ---------------------------------------------------
    # ------------------------------------------------------------------

    async def run(self) -> dict[Power, int]:
        """Run the match to completion – returns final supply-centre counts."""
        while not self.engine.get_game_state().is_game_done:
            await self._play_turn()

        # Capture final board state after the game concludes.
        self.engine.capture_frame()

        # Persist full game data and board animation.
        self.engine.save(f"game_saves/game_state{self._file_suffix}.datc")
        self.engine.save_animation(f"board_svg/board_animation{self._file_suffix}.svg")

        total_cost = sum(self._cost_usd_by_power.values())
        logger.info("Total LLM cost: $%.4f", total_cost)
        logger.info(f"Total LLM cost across all powers: ${total_cost:.5f}")

        total_runtime = sum(self._runtime_s_by_power.values())
        logger.info("Total agent runtime: %.2f s", total_runtime)
        logger.info(f"Total agent runtime across all powers: {total_runtime:.2f}s")

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

    # ------------------------------------------------------------------
    # High-level per-phase driver --------------------------------------
    # ------------------------------------------------------------------

    async def _play_turn(self) -> None:
        """Run orders every phase and public press only during movement phases."""
        # Public press only makes sense during Movement phases ("M"). Skip
        # press rounds in Adjustment (builds/disbands) and Retreat phases to
        # reduce unnecessary LLM calls and cluttered history.
        state = self.engine.get_game_state()
        if state.phase_type == "M":
            # 1. Public press (up to 3 rounds) -----------------------------
            await self._run_public_press_rounds()

        # 2. Orders -------------------------------------------------------
        await self._run_orders_phase()

    # Retain old name as thin wrapper for backward compatibility.
    async def _run_single_phase(self) -> None:  # pragma: no cover
        await self._play_turn()

    # ------------------------------------------------------------------
    # Press handling -----------------------------------------------------
    # ------------------------------------------------------------------

    async def _run_public_press_rounds(self) -> None:
        """Execute up to 10 asynchronous public-press rounds."""
        for _ in range(3):
            state = self.engine.get_game_state()

            # Launch one press task per *living* power (skip eliminated ones).
            tasks: dict[Power, asyncio.Task[str]] = {}
            for power in state.all_powers:
                view = self.engine.get_power_view(power)
                task = asyncio.create_task(self.agents[power].get_press_message(state, view))
                tasks[power] = task

            await asyncio.gather(*tasks.values())

            round_messages: list[str] = []
            for power, task in tasks.items():
                msg = task.result().strip()
                if msg:  # ignore empty strings
                    formatted = f"{power}: {msg}"
                    round_messages.append(formatted)

                    # Persist via underlying diplomacy engine.
                    self.engine.add_public_message(power, msg)

                # Update running cost/runtime tallies for LLM agents.
                agent = self.agents[power]
                if isinstance(agent, LLMAgent):
                    self._cost_usd_by_power[power] = agent.total_cost_usd
                    self._runtime_s_by_power[power] = agent.total_runtime_s

            # Stop early if everyone stayed silent.
            if not round_messages:
                break

        # Share updated history with agents for future prompts.
        full_history = list(self.engine.get_game_state().press_history)
        for agent in self.agents.values():
            agent.press_history = full_history

    # ------------------------------------------------------------------
    # Orders handling ----------------------------------------------------
    # ------------------------------------------------------------------

    async def _run_orders_phase(self) -> None:
        """Collect orders from all surviving powers and process the phase."""
        # Log current supply‐centre distribution for easier debugging/analysis.
        state = self.engine.get_game_state()
        logger.info(f"{state.phase}: {state.all_supply_center_counts}")

        # Kick off one asynchronous orders task per surviving power.
        tasks: dict[Power, asyncio.Task[Orders]] = {}
        for power in state.all_powers:
            view = self.engine.get_power_view(power)
            if not view.orders_list:  # eliminated – skip
                continue
            tasks[power] = asyncio.create_task(self.agents[power].get_orders(state, view))

        if not tasks:
            return  # all powers eliminated – game should be over

        await asyncio.gather(*tasks.values())

        for power, task in tasks.items():
            self.engine.submit_orders(power, task.result())

            agent = self.agents[power]
            if isinstance(agent, LLMAgent):
                self._cost_usd_by_power[power] = agent.total_cost_usd
                self._runtime_s_by_power[power] = agent.total_runtime_s

        # Debug‐level running totals.
        cost_by_power = dict(self._cost_usd_by_power)
        logger.debug(f"Running Cost (USD): {sum(cost_by_power.values()):.2f} ({cost_by_power})")

        runtime_by_power = dict(self._runtime_s_by_power)
        logger.debug(f"Running Runtime (s): {sum(runtime_by_power.values()):.2f} ({runtime_by_power})")

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
