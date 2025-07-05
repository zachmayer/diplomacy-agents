# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
"""Minimal typed wrapper around the diplomacy package."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

import drawsvg as draw
from diplomacy import Game as _RawGame
from diplomacy.engine.message import Message
from diplomacy.engine.renderer import Renderer
from diplomacy.utils import export
from pydantic import BaseModel, ConfigDict

from diplomacy_agents.literals import Location, PhaseType, Power, UnitType

# ---------------------------------------------------------------------------
# Typings
# ---------------------------------------------------------------------------


type Orders = list[str]  # TODO: should this be a tuple?


@runtime_checkable
class _GameProtocol(Protocol):
    """Subset of the ``diplomacy.Game`` interface required by this wrapper."""

    # Public attributes -----------------------------------------------------
    # Underlying engine maps power name to Power class instance. We don't use the Power class instance.
    powers: dict[Power, Any]
    phase_type: PhaseType  # e.g. "M"
    phase: str  # Long phase name, e.g. "SPRING 1901 MOVEMENT"
    is_game_done: bool  # True if the game is over

    # Messaging helpers ---------------------------------------------------
    def add_message(self, message: Message) -> int: ...

    # Shorthand phase token like "S1901M" (used when creating Message objects)
    current_short_phase: str  # e.g. "S1901M"

    # Public methods --------------------------------------------------------
    def get_current_phase(self) -> str: ...

    def get_centers(self, power: Power) -> list[Location]: ...

    def get_units(self, power: Power) -> list[UnitType]: ...

    def get_all_possible_orders(self) -> dict[Location, Orders]: ...

    def get_orderable_locations(self, power: Power | None = None) -> list[Location]: ...

    def set_orders(self, power: Power, orders: Orders) -> None: ...

    def process(self) -> None: ...


# ---------------------------------------------------------------------------
# Data-transfer objects (DTOs)
# ---------------------------------------------------------------------------


class GameStateDTO(BaseModel):
    """Immutable container with coarse, *global* game information."""

    model_config = ConfigDict(strict=True, frozen=True)

    # Scalars -----------------------------------------------------------------
    is_game_done: bool
    phase: str  # compact phase token, e.g. "S1901M"
    phase_long: str  # human‐friendly phase string, e.g. "SPRING 1901 MOVEMENT"
    phase_type: PhaseType
    year: int

    # Collections -------------------------------------------------------------
    all_powers: tuple[Power, ...]
    all_supply_center_counts: dict[Power, int]
    all_supply_center_locations: dict[Power, tuple[Location, ...]]
    all_unit_locations: dict[Power, dict[Location, UnitType]]
    press_history: tuple[str, ...]


class PowerViewDTO(BaseModel):
    """Perspective-specific snapshot for *one* power."""

    model_config = ConfigDict(strict=True, frozen=True)

    # Scalars -----------------------------------------------------------------
    power: Power

    # Collections -------------------------------------------------------------
    # TODO: should these be "your" instead of "my"?
    my_supply_center_count: int
    my_unit_locations: dict[Location, UnitType]
    my_home_supply_center_locations: tuple[Location, ...]
    my_supply_center_locations: tuple[Location, ...]
    my_orders_by_location: dict[Location, tuple[str, ...]]

    @property
    def orders_list(self) -> Orders:
        """Return a single flat ``list`` containing all legal order strings."""
        return [order for opts in self.my_orders_by_location.values() for order in opts]


# ---------------------------------------------------------------------------
# Engine façade
# ---------------------------------------------------------------------------


class DiplomacyEngine:
    """Very thin wrapper exposing just the bits we need."""

    def __init__(self, *, rules: set[str] | None = None) -> None:
        """Create a new Diplomacy game instance."""
        default_rules: set[str] = {"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"}
        raw_game = _RawGame(rules=rules or default_rules)
        self._game: _GameProtocol = cast(_GameProtocol, raw_game)
        self.svg_frames: list[str] = []
        # Cumulative public‐press history (strings formatted as "POWER: message").
        self._press_history: list[str] = []

    def get_game_state(self) -> GameStateDTO:
        """Return a coarse snapshot of the entire game."""
        phase_token = self._game.get_current_phase()  # e.g. "S1901M"

        return GameStateDTO(
            is_game_done=self._game.is_game_done,
            phase=phase_token,
            phase_long=str(self._game.phase),
            phase_type=self._game.phase_type,
            year=int(phase_token[1:5]) if len(phase_token) >= 5 and phase_token[1:5].isdigit() else 0,
            all_powers=tuple(self._game.powers),
            all_supply_center_counts={p: len(self._game.get_centers(p)) for p in self._game.powers},
            all_supply_center_locations={p: tuple(self._game.get_centers(p)) for p in self._game.powers},
            all_unit_locations=self._get_units_by_power(),
            press_history=tuple(self._press_history),
        )

    def get_power_view(self, power: Power) -> PowerViewDTO:
        """Return the board from *power*'s perspective."""
        all_possible: dict[Location, Orders] = self._game.get_all_possible_orders()
        orderable: tuple[Location, ...] = tuple(self._game.get_orderable_locations(power))

        valid: dict[Location, tuple[str, ...]] = {
            loc: tuple(all_possible[loc]) for loc in orderable if loc in all_possible
        }

        # Parse unit list like ["A PAR", "F BRE"] into {"PAR": "A", "BRE": "F"}
        units_map: dict[Location, UnitType] = {}
        for unit_str in self._game.get_units(power):
            unit_type, loc = self._split_unit(unit_str)
            units_map[loc] = unit_type

        # Home supply centres where *power* can build.
        # The underlying diplomacy engine stores them on the per-power object
        # under the ``homes`` attribute.
        homes_raw: tuple[Location, ...] = tuple(cast(list[Location], self._game.powers[power].homes))

        return PowerViewDTO(
            power=power,
            my_supply_center_count=len(self._game.get_centers(power)),
            my_home_supply_center_locations=homes_raw,
            my_supply_center_locations=tuple(self._game.get_centers(power)),
            my_unit_locations=units_map,
            my_orders_by_location=valid,
        )

    def submit_orders(self, power: Power, orders: Orders) -> None:
        """Submit list of DATC order strings for *power*."""
        self._game.set_orders(power, orders)

    def process_turn(self) -> None:
        """Advance the game one phase while recording a snapshot *before* the move."""
        # Capture the board state *before* orders are resolved so the animation shows
        # the pre‐resolution position for every phase
        self.capture_frame()

        # Resolve the phase in the underlying engine.
        self._game.process()

    def capture_frame(self) -> None:
        """Append the current board SVG to the internal frame buffer."""
        renderer: Callable[..., str] = Renderer(self._game).render
        svg_xml: str = renderer(incl_orders=True, incl_abbrev=True)
        self.svg_frames.append(svg_xml)

    def save_animation(self, output_path: str) -> None:
        """Create a simple SMIL animation from ``self.svg_frames`` using drawsvg."""
        if not self.svg_frames:
            return

        fps = 2
        duration = len(self.svg_frames) / fps
        config = draw.types.SyncedAnimationConfig(
            duration=duration,  # Seconds
            show_playback_progress=True,
            show_playback_controls=True,
        )

        d = draw.Drawing(1200, 850, animation_config=config)
        for i, svg in enumerate(self.svg_frames):
            img_any: Any = draw.Image(0, 0, 1200, 850, data=svg.encode("utf-8"), mime_type="image/svg+xml")
            img_any.add_key_frame(i / fps, opacity=0)
            img_any.add_key_frame(i / fps + 0.01, opacity=1)
            img_any.add_key_frame(i / fps + 1, opacity=1)
            img_any.add_key_frame(i / fps + 1.01, opacity=0)
            d.append(img_any)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        d.save_svg(output_path)

    def save(self, file_path: str) -> None:
        """Write the current game to *file_path* in DATC JSON format."""
        export.to_saved_game_format(self._game, file_path, "w")

    # --------------------------------------------------------------
    # Public press -------------------------------------------------
    # --------------------------------------------------------------

    def add_public_message(self, sender: Power, message: str) -> None:  # noqa: D401
        """Forward a public‐press message to the underlying diplomacy engine."""
        from diplomacy.engine.message import GLOBAL, Message

        # Build and record a server-side message object.
        self._game.add_message(
            Message(
                phase=self._game.current_short_phase,
                sender=sender,
                recipient=GLOBAL,
                message=message,
            )
        )

        # Keep a plain-text copy for easy prompt inclusion.
        self._press_history.append(f"{sender}: {message}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _split_unit(unit_str: str) -> tuple[UnitType, Location]:
        """Parse a unit string like 'A PAR' into typed components."""
        unit_type_str, loc_str = unit_str.split(" ", 1)
        return cast(UnitType, unit_type_str), cast(Location, loc_str)

    def _get_units_by_power(self) -> dict[Power, dict[Location, UnitType]]:
        """Return {power: {loc: unit_type}} nested mapping for all units."""
        mp: dict[Power, dict[Location, UnitType]] = {}
        for power in self._game.powers:
            per_power: dict[Location, UnitType] = {}
            for unit_str in self._game.get_units(power):
                unit_type, loc = self._split_unit(unit_str)
                per_power[loc] = unit_type
            mp[power] = per_power
        return mp

    def _get_dislodged_locations(self) -> list[Location]:
        """Return locations of units that are currently dislodged."""
        dislodged: list[Location] = []
        for power in self._game.powers:
            for unit_str in self._game.get_units(power):
                unit_type, loc = self._split_unit(unit_str)
                if unit_type.startswith("*"):
                    dislodged.append(loc)
        return dislodged


__all__ = [
    "DiplomacyEngine",
    "GameStateDTO",
    "PowerViewDTO",
    "Power",
    "Location",
    "UnitType",
    "PhaseType",
    "Orders",
]
