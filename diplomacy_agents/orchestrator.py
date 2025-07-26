"""Asynchronous self-play driver orchestrating seven agents (LLMs or baselines)."""

from __future__ import annotations

import asyncio

# ---------------------------------------------------------------------------#
# Imports                                                                  #
# ---------------------------------------------------------------------------#
import logging
from pathlib import Path
from typing import Literal

from drawsvg import Drawing, Image, types
from pydantic import BaseModel, ConfigDict
from pydantic_ai.models import KnownModelName

from diplomacy_agents.agents import BaseAgent, HoldAgent, LLMAgent, RandomAgent
from diplomacy_agents.engine import DiplomacyEngine, Orders
from diplomacy_agents.enums import Power

__all__ = ["GameOrchestrator", "PowerModelMap", "HoldModelMap", "RandomModelMap"]


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------#
# Typing helpers                                                             #
# ---------------------------------------------------------------------------#

AgentSpecName = KnownModelName | Literal["hold", "random"]


# Removed lightweight wrappers; we now use ``drawsvg`` classes directly.


class PowerModelMap(BaseModel):
    """Simple Pydantic model mapping each *Power* to its agent spec."""

    AUSTRIA: AgentSpecName
    ENGLAND: AgentSpecName
    FRANCE: AgentSpecName
    GERMANY: AgentSpecName
    ITALY: AgentSpecName
    RUSSIA: AgentSpecName
    TURKEY: AgentSpecName

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        use_enum_values=True,
    )


# All powers hold
HoldModelMap = PowerModelMap(
    AUSTRIA="hold",
    ENGLAND="hold",
    FRANCE="hold",
    GERMANY="hold",
    ITALY="hold",
    RUSSIA="hold",
    TURKEY="hold",
)

# All powers move randomly
RandomModelMap = PowerModelMap(
    AUSTRIA="random",
    ENGLAND="random",
    FRANCE="random",
    GERMANY="random",
    ITALY="random",
    RUSSIA="random",
    TURKEY="random",
)

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class GameOrchestrator:
    """Coordinate the Diplomacy engine with seven autonomous agents."""

    def __init__(
        self,
        *,
        model_map: PowerModelMap,
        max_year: int | None = 1951,
    ) -> None:
        """
        Create a new orchestrator.

        *model_map* assigns each *Power* to an agent spec (`"hold"`, `"random"`
        or a concrete LLM model name).  No randomness is introduced here; call
        sites supply the full mapping.
        """
        self._max_year: int | None = max_year

        self.engine = DiplomacyEngine()
        self.svg_frames: list[str] = []  # SVG board snapshots (one per phase)
        self.model_map: PowerModelMap = model_map
        self.agents: dict[Power, BaseAgent] = self._init_agents()

    # ------------------------------------------------------------------
    # Public control flow
    # ------------------------------------------------------------------

    async def play_turn(self) -> None:
        """Execute one phase: snapshot, gather orders, advance game."""
        await self._run_orders_phase()
        self._capture_frame()
        self._log_running_totals()
        self.engine.process_turn()

    async def run(self) -> dict[Power, int]:
        """Run until game end (or *max_year* cap) and return final SC counts."""
        logger.info("Initial model map: %s", self.model_map)

        while not self.engine.is_done:
            await self.play_turn()
            logger.info("%s: %s", self.engine.short_phase, self.engine.supply_center_counts)

            if self._max_year is not None and self.engine.year >= self._max_year:
                logger.info(
                    "Reached year %d (cap %d) – terminating early.",
                    self.engine.year,
                    self._max_year,
                )
                break

        # Final board snapshot
        self._capture_frame()

        total_runtime = sum(a.total_runtime_s for a in self.agents.values())
        logger.info("Total agent runtime: %.2f s", total_runtime)

        return self.engine.supply_center_counts

    # ------------------------------------------------------------------
    # Agent initialization & logging
    # ------------------------------------------------------------------

    def _init_agents(self) -> dict[Power, BaseAgent]:
        """Instantiate one agent per power according to *self.model_map*."""
        agents: dict[Power, BaseAgent] = {}
        for power in self.engine.powers:
            spec = getattr(self.model_map, power.name)
            if spec == "hold":
                agents[power] = HoldAgent(power)
            elif spec == "random":
                agents[power] = RandomAgent(power)
            else:
                agents[power] = LLMAgent(power, spec)
        return agents

    def _log_running_totals(self) -> None:
        """Emit debug-level cumulative runtime per power."""
        runtimes = {p: a.total_runtime_s for p, a in self.agents.items()}
        logger.debug("Cumulative runtime (s): %.2f %s", sum(runtimes.values()), runtimes)

    # ------------------------------------------------------------------
    # Orders phase
    # ------------------------------------------------------------------

    async def _run_orders_phase(self) -> None:
        """Collect orders from surviving powers and submit to the engine."""
        tasks: dict[Power, asyncio.Task[Orders]] = {}
        for power in self.engine.surviving_powers:
            flat_orders = self.engine.flat_possible_orders[power]
            if not flat_orders:
                continue
            tasks[power] = asyncio.create_task(self.agents[power].get_orders(self.engine))

        if not tasks:  # no orders to collect
            return

        await asyncio.gather(*tasks.values())
        for power, task in tasks.items():
            self.engine.set_orders(power, task.result())

    # ------------------------------------------------------------------
    # Snapshot / animation helpers
    # ------------------------------------------------------------------

    def _capture_frame(self) -> None:
        """Render current board to SVG and append to the frame buffer."""
        self.svg_frames.append(self.engine.render_svg(incl_orders=True, incl_abbrev=True))

    def save_animation(self, output_path: Path | str) -> None:
        """Write buffered SVG frames to a SMIL animation (drawsvg)."""
        if not self.svg_frames:
            return

        path = Path(output_path)
        fps = 2
        duration = len(self.svg_frames) / fps
        config = types.SyncedAnimationConfig(
            duration=duration,
            show_playback_progress=True,
            show_playback_controls=True,
        )

        drawing = Drawing(1150, 850, animation_config=config)
        for i, svg in enumerate(self.svg_frames):
            img = Image(0, 0, 1200, 850, data=svg.encode(), mime_type="image/svg+xml")
            img.add_key_frame(i / fps, opacity=0)
            img.add_key_frame(i / fps + 0.01, opacity=1)
            img.add_key_frame(i / fps + 1, opacity=1)
            img.add_key_frame(i / fps + 1.01, opacity=0)
            drawing.append(img)

        path.parent.mkdir(parents=True, exist_ok=True)
        drawing.save_svg(str(path))
