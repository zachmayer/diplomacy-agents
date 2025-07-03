"""Minimal typed wrapper around the diplomacy package."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

# Third-party diplomacy engine ------------------------------------------------
from diplomacy import Game as _RawGame
from diplomacy.engine.renderer import Renderer
from diplomacy.utils import export as _export  # type: ignore[import-not-found]
from pydantic import BaseModel, ConfigDict

# Canonical token literals ---------------------------------------------------
from diplomacy_agents.literals import Location, PhaseType, Power, UnitType

# ---------------------------------------------------------------------------
# Generic order list model
# ---------------------------------------------------------------------------


type Orders = list[str]


# ---------------------------------------------------------------------------
# Typing for `diplomacy.Game`
# ---------------------------------------------------------------------------


# Note: ``diplomacy.Game`` exposes ``powers`` as a mapping from power name to
# ``diplomacy.engine.power.Power`` instances.  We only rely on the keys here
# but expose the value type loosely as ``Any`` since we don't access the full
# third-party attributes beyond the few needed below.


@runtime_checkable
class _GameProtocol(Protocol):
    """Subset of the ``diplomacy.Game`` interface required by this wrapper."""

    # Public attributes -----------------------------------------------------
    powers: dict[Power, Any]
    phase_type: PhaseType
    phase: str  # long phase name, e.g. "SPRING 1901 MOVEMENT"
    is_game_done: bool

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

    # Collections prefixed with ``all_`` to emphasise board‐wide scope --------
    all_powers: tuple[Power, ...]
    all_supply_center_counts: dict[Power, int]
    all_supply_center_locations: dict[Power, tuple[Location, ...]]
    all_unit_locations: dict[Power, dict[Location, UnitType]]


class PowerViewDTO(BaseModel):
    """Perspective-specific snapshot for *one* power."""

    model_config = ConfigDict(strict=True, frozen=True)

    power: Power  # owning power token (scalar – no prefix)

    # Collections are prefixed with ``my_`` to clarify they're for this power.
    my_supply_center_count: int
    my_unit_locations: dict[Location, UnitType]
    my_home_supply_center_locations: tuple[Location, ...]
    my_supply_center_locations: tuple[Location, ...]
    my_orders_by_location: dict[Location, tuple[str, ...]]

    @property
    def orders_list(self) -> list[str]:
        """Return a single flat ``list`` containing all legal order strings."""
        return [order for opts in self.my_orders_by_location.values() for order in opts]


# ---------------------------------------------------------------------------
# Engine façade
# ---------------------------------------------------------------------------


class DiplomacyEngine:
    """Very thin wrapper exposing just the bits we need."""

    def __init__(self, *, rules: set[str] | None = None) -> None:
        """Create a new Diplomacy game instance."""
        # Use deadline-free rules by default so the driver controls phase ticks.
        default_rules: set[str] = {"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"}
        raw_game = _RawGame(rules=rules or default_rules)
        # Narrow the untyped third-party object to the subset we officially rely on.
        self._game: _GameProtocol = cast(_GameProtocol, raw_game)

        # Collect SVG snapshots for later animation export.
        self.svg_frames: list[str] = []

    def get_game_state(self) -> GameStateDTO:
        """Return a coarse snapshot of the entire game."""
        phase_token = self._game.get_current_phase()  # e.g. "S1901M"

        return GameStateDTO(
            is_game_done=self._game.is_game_done,
            phase=phase_token,
            phase_long=str(self._game.phase),
            phase_type=self._get_phase_type(),
            year=int(phase_token[1:5]) if len(phase_token) >= 5 and phase_token[1:5].isdigit() else 0,
            all_powers=tuple(self._game.powers),
            all_supply_center_counts={p: len(self._game.get_centers(p)) for p in self._game.powers},
            all_supply_center_locations={p: tuple(self._game.get_centers(p)) for p in self._game.powers},
            all_unit_locations=self._get_units_by_power(),
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
        unit_strings = self._game.get_units(power)
        for unit_str in unit_strings:
            unit_type_str, loc_str = unit_str.split(" ", 1)
            unit_type = cast(UnitType, unit_type_str)
            loc = cast(Location, loc_str)
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
        # the pre‐resolution position for every phase – mirroring the previous
        # behaviour implemented in the orchestrator.
        self.capture_frame()

        # Resolve the phase in the underlying engine.
        self._game.process()

    def capture_frame(self) -> None:
        """Append the current board SVG to the internal frame buffer."""
        self.svg_frames.append(self.svg_string())

    def save(self, file_path: str) -> None:
        """Write the current game to *file_path* in DATC JSON format."""
        # Cast the third‐party helper to ``Any`` *before* attribute access so
        # static analysis tools don't attempt to inspect its (untyped) internals.
        _save_game: Callable[[Any, str | None, str], dict[str, Any]] = cast(Any, _export).to_saved_game_format
        _save_game(self._game, file_path, "w")

    def save_animation(self, output_path: str, frame_duration: float = 0.75) -> None:
        """
        Write collected SVG snapshots to *output_path*.

        The *frame_duration* parameter is accepted for backward compatibility
        but is currently ignored.  Callers can pass the argument without
        affecting behaviour, keeping the public interface stable.
        """
        _ = frame_duration  # Preserve signature while silencing unused‐arg linters.

        # Persist the *final* captured frame.  A more sophisticated animation
        # export can be implemented later using the in-memory buffer.
        if self.svg_frames:
            path_obj = Path(output_path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            path_obj.write_text(self.svg_frames[-1])

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def svg_string(self, *, show_orders: bool = True) -> str:
        """
        Return an SVG snapshot of the current board state.

        Thin wrapper around ``diplomacy.utils.export.render_board_svg``.
        The upstream helper returns a plain SVG string generated entirely in
        Python – no external Cairo or other native libraries are needed.
        """
        renderer: Callable[..., str] = cast(Any, Renderer(self._game)).render
        svg_xml: str = renderer(incl_orders=show_orders, output_format="svg")
        return svg_xml

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_phase_type(self) -> PhaseType:
        """Map diplomacy engine phase constant to single-letter code."""
        pt_raw: str = self._game.phase_type
        mapping: dict[str, PhaseType] = {
            "M": "M",
            "MOVEMENT": "M",
            "R": "R",
            "RETREATS": "R",
            "A": "A",
            "ADJUSTMENT": "A",
            "ADJUSTMENTS": "A",
        }
        # Default to "M" (movement) for unrecognised or terminal tokens such
        # as "-" or "COMPLETE" – phase‐type is irrelevant once the game ends
        # but we still need a valid single‐letter value to satisfy the alias.
        return mapping.get(pt_raw, "M")

    # ------------------------------------------------------------------
    # Board-wide helpers
    # ------------------------------------------------------------------

    def _get_units_by_power(self) -> dict[Power, dict[Location, UnitType]]:
        """Return {power: {loc: unit_type}} nested mapping for all units."""
        mp: dict[Power, dict[Location, UnitType]] = {}
        for power in self._game.powers:
            unit_strings = self._game.get_units(power)
            per_power: dict[Location, UnitType] = {}
            for unit_str in unit_strings:
                unit_type_str, loc_str = unit_str.split(" ", 1)
                unit_type_clean = unit_type_str.lstrip("*?")
                loc = cast(Location, loc_str)
                per_power[loc] = cast(UnitType, unit_type_clean)
            mp[power] = per_power
        return mp

    def _get_dislodged_locations(self) -> list[Location]:
        """Return locations of units that are currently dislodged."""
        dislodged: list[Location] = []
        for power in self._game.powers:
            unit_strings = self._game.get_units(power)
            for unit_str in unit_strings:
                unit_type_str, loc_str = unit_str.split(" ", 1)
                if unit_type_str.startswith("*"):
                    dislodged.append(cast(Location, loc_str))
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
