"""Asynchronous self-play driver orchestrating seven agents (LLMs or baselines)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import drawsvg as draw
from pydantic_ai.models import KnownModelName

from diplomacy_agents.agents import (
    BaseAgent,
    HoldAgent,
    LLMAgent,
    RandomAgent,
)
from diplomacy_agents.engine import DiplomacyEngine, GameStateDTO, Orders, Power

AgentSpecName = KnownModelName | Literal["hold", "random"]


class _SvgImageLike(Protocol):  # pragma: no cover
    """Subset of the ``drawsvg.Image`` interface used here (only ``add_key_frame``)."""

    def add_key_frame(self, time: float, *, opacity: float) -> None: ...


class _SvgDrawingLike(Protocol):  # pragma: no cover
    """Subset of the ``drawsvg.Drawing`` interface we rely on."""

    def append(self, element: _SvgImageLike, *, z: int | None = None) -> None: ...

    def save_svg(self, fname: str, encoding: str = "utf-8", context: None | dict[str, Any] = None) -> None: ...


class PowerModelMap(dict[Power, AgentSpecName]):
    """Mapping from each power to its agent specification."""

    ENGLAND: AgentSpecName
    FRANCE: AgentSpecName
    GERMANY: AgentSpecName
    ITALY: AgentSpecName
    RUSSIA: AgentSpecName
    TURKEY: AgentSpecName
    AUSTRIA: AgentSpecName


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def surviving_powers(state: GameStateDTO) -> tuple[Power, ...]:
    """Return a tuple of powers that still control ≥1 supply centre."""
    return tuple(p for p, cnt in state.all_supply_center_counts.items() if cnt > 0)


__all__ = ["GameOrchestrator", "run_game", "PowerModelMap"]


# ---------------------------------------------------------------------------
# Module-level logger --------------------------------------------------------
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# High-level orchestrator -----------------------------------------------------
# ---------------------------------------------------------------------------


class GameOrchestrator:
    """High-level game loop coordinating the engine and seven agents."""

    def __init__(
        self,
        *,
        model_map: PowerModelMap,
        messaging_rounds: int = 3,
        max_year: int | None = 1951,
    ) -> None:
        """
        Create a new orchestrator bound to an explicit *model_map*.

        The constructor is now *deterministic* – callers must provide the
        complete ``Power → model`` mapping so there is no hidden randomness.
        """
        # 0 rounds = gunboat (no press).
        self.MESSAGING_ROUNDS: int = messaging_rounds
        self._max_year: int | None = max_year

        self.engine = DiplomacyEngine()
        # Buffer of raw SVG strings captured throughout the game (one per phase)
        self.svg_frames: list[str] = []

        # Freeze power → model mapping.
        self.model_map: PowerModelMap = model_map

        # Instantiate the agents.
        self.agents: dict[Power, BaseAgent] = self._init_agents()

        # Messaging removed – no press log required in gunboat mode.

    # ------------------------------------------------------------------
    # Main public API ---------------------------------------------------
    # ------------------------------------------------------------------

    async def play_turn(self) -> None:
        """Run all the parts of a single turn (one phase advance)."""
        # Record board before any new orders/messages.
        self._capture_frame()

        self.engine.get_game_state()
        await self._run_orders_phase()
        self._log_running_totals()
        self.engine.process_turn()

    async def run(self) -> dict[Power, int]:
        """Run the match to completion - returns final supply-centre counts."""
        logger.info("Initial model map: %s", self.model_map)
        while not self.engine.get_game_state().is_game_done:
            await self.play_turn()
            state = self.engine.get_game_state()
            logger.info(f"{state.short_phase}: {state.all_supply_center_counts}")

            # Optional early-termination guard to prevent endless stalemates.
            if self._max_year is not None and state.year >= self._max_year:
                logger.info(
                    "Reached year %d (cap %d) – terminating self-play early.",
                    state.year,
                    self._max_year,
                )
                break

        # Capture final board state after the game concludes.
        self._capture_frame()

        total_runtime = sum(a.total_runtime_s for a in self.agents.values())

        # Token cost aggregation happens in ExperimentRunner; avoid duplication here.
        logger.info("Total agent runtime: %.2f s", total_runtime)

        logger.debug(f"Total agent runtime across all powers: {total_runtime:.2f}s")

        # No file I/O here – experiment layer handles persistence.

        return self.engine.get_game_state().all_supply_center_counts

    # ------------------------------------------------------------------
    # Internals ---------------------------------------------------------
    # ------------------------------------------------------------------

    def _init_agents(self) -> dict[Power, BaseAgent]:
        """Create and return the immutable power → agent mapping."""
        state = self.engine.get_game_state()

        agents: dict[Power, BaseAgent] = {}
        for p in state.all_supply_center_counts:
            spec = self.model_map[p]
            if spec == "hold":
                agents[p] = HoldAgent(p)
            elif spec == "random":
                agents[p] = RandomAgent(p)
            else:
                agents[p] = LLMAgent(p, spec)
        return agents

    def _log_running_totals(self) -> None:
        """Emit debug-level summary of cumulative cost and runtime."""
        runtime_by_power = {p: a.total_runtime_s for p, a in self.agents.items()}
        logger.debug(f"Running Runtime (s): {sum(runtime_by_power.values()):.2f} ({runtime_by_power})")

    # Messaging handling removed entirely – gunboat mode has no press phase.

    # ------------------------------------------------------------------
    # Orders handling ----------------------------------------------------
    # ------------------------------------------------------------------

    async def _run_orders_phase(self) -> None:
        """Collect orders from all surviving powers and process the phase."""
        # Log current supply‐centre distribution for easier debugging/analysis.
        state = self.engine.get_game_state()

        # Kick off one asynchronous orders task per surviving power.
        tasks: dict[Power, asyncio.Task[Orders]] = {}
        for power in surviving_powers(state):
            view = self.engine.get_power_view(power)
            if not view.legal_orders_list:  # No possible orders – skip
                continue
            tasks[power] = asyncio.create_task(self.agents[power].get_orders(state, view))

        if not tasks:
            return  # No power has possible orders: proceed to next phase (e.g. game over, or no builds in build phase)

        await asyncio.gather(*tasks.values())

        for power, task in tasks.items():
            self.engine.submit_orders(power, task.result())

    # ------------------ Snapshot / animation helpers -------------------

    def _capture_frame(self) -> None:
        """Render the current board and append the SVG string to the buffer."""
        svg_xml = self.engine.render_svg(incl_orders=True, incl_abbrev=True)
        self.svg_frames.append(svg_xml)

    # Renamed from *_save_animation* to make it part of the public surface.
    def save_animation(self, output_path: Path | str) -> None:
        """Persist ``self.svg_frames`` as a simple SMIL animation (drawsvg)."""
        if not self.svg_frames:
            return

        path_obj = Path(output_path)

        fps = 2
        duration = len(self.svg_frames) / fps
        config = draw.types.SyncedAnimationConfig(
            duration=duration,
            show_playback_progress=True,
            show_playback_controls=True,
        )

        d = cast(_SvgDrawingLike, draw.Drawing(1200, 850, animation_config=config))
        for i, svg in enumerate(self.svg_frames):
            img = cast(
                _SvgImageLike,
                draw.Image(
                    0,
                    0,
                    1200,
                    850,
                    data=svg.encode("utf-8"),
                    mime_type="image/svg+xml",
                ),
            )
            img.add_key_frame(i / fps, opacity=0)
            img.add_key_frame(i / fps + 0.01, opacity=1)
            img.add_key_frame(i / fps + 1, opacity=1)
            img.add_key_frame(i / fps + 1.01, opacity=0)
            d.append(img)

        path_obj.parent.mkdir(parents=True, exist_ok=True)
        d.save_svg(str(path_obj))

    # press_entries property removed – no press in gunboat mode.


def run_game(
    *,
    model_map: PowerModelMap,
    messaging_rounds: int = 3,
    max_year: int | None = 1951,
) -> dict[Power, int]:
    """
    Blocking helper for synchronous callers (e.g. CLI).

    This thin wrapper mirrors ``GameOrchestrator``'s keyword parameters so it
    can be used interchangeably in simple scripts.
    """

    async def _runner() -> dict[Power, int]:
        orch = GameOrchestrator(
            model_map=model_map,
            messaging_rounds=messaging_rounds,
            max_year=max_year,
        )
        return await orch.run()

    return asyncio.run(_runner())
