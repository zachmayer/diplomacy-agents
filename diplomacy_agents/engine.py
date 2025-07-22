# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
"""Minimal typed wrapper around the diplomacy package."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, TypeVar, cast, runtime_checkable

from diplomacy import Game as _RawGame
from diplomacy.engine.renderer import Renderer
from diplomacy.utils import export
from pydantic import BaseModel, ConfigDict

from diplomacy_agents.literals import Location, PhaseType, Power, UnitType

__all__ = [
    "Orders",
    "GameStateDTO",
    "PowerViewDTO",
    "DiplomacyEngine",
]

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
    short_phase: str  # compact phase token, e.g. "S1901M"
    phase: str  # human‐friendly phase string, e.g. "SPRING 1901 MOVEMENT"
    phase_type: PhaseType
    year: int

    # Collections -------------------------------------------------------------
    all_powers: tuple[Power, ...]
    all_supply_center_counts: dict[Power, int]
    all_supply_center_locations: dict[Power, tuple[Location, ...]]
    all_unit_locations: dict[Power, dict[Location, UnitType]]


class PowerViewDTO(BaseModel):
    """Perspective-specific snapshot for *one* power."""

    model_config = ConfigDict(strict=True, frozen=True, arbitrary_types_allowed=False)

    # Scalars -----------------------------------------------------------------
    power: Power

    # Collections -------------------------------------------------------------
    # TODO: should these be "your" instead of "my"?
    my_supply_center_count: int
    my_supply_center_locations: tuple[Location, ...]
    my_home_supply_center_locations: tuple[Location, ...]
    my_unit_locations: dict[Location, UnitType]
    my_possible_orders_by_location: dict[Location, tuple[str, ...]]

    @property
    def legal_orders_list(self) -> Orders:
        """Return a single flat ``list`` containing all legal order strings."""
        return [order for opts in self.my_possible_orders_by_location.values() for order in opts]


# ---------------------------------------------------------------------------
# Engine façade
# ---------------------------------------------------------------------------

K = TypeVar("K")
V = TypeVar("V")


def sorted_by_key[K, V](mapping: Mapping[K, V]) -> dict[K, V]:
    """Return a **new** dict with items ordered by key (ascending)."""
    return dict(sorted(mapping.items()))


def _split_unit(unit_str: str) -> tuple[UnitType, Location]:
    """Parse a unit string like 'A PAR' into typed components."""
    unit_type_str, loc_str = unit_str.split(" ", 1)
    return cast(UnitType, unit_type_str), cast(Location, loc_str)


class DiplomacyEngine:
    """Wrapper around the diplomacy package engine."""

    def __init__(self, *, rules: set[str] | None = None) -> None:
        """Create a new Diplomacy game instance."""
        default_rules: set[str] = {"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"}
        raw_game = _RawGame(rules=rules or default_rules)
        self._game: _GameProtocol = cast(_GameProtocol, raw_game)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def extract_year_from_phase(self, phase_token: str) -> int | None:
        """Return the four-digit year component from a phase token like "S1901M"."""
        if len(phase_token) >= 5 and phase_token[1:5].isdigit():
            return int(phase_token[1:5])
        return None

    def get_powers(self) -> tuple[Power, ...]:
        """Return the list of powers."""
        return tuple(sorted(Power(p) for p in self._game.powers))

    def get_power_supply_centers(self, power: Power) -> tuple[Location, ...]:
        """Return the list of centers for a power."""
        return tuple(sorted(self._game.get_centers(power)))

    def get_all_supply_centers(self) -> dict[Power, tuple[Location, ...]]:
        """Return the list of centers for all powers."""
        centers = {p: self.get_power_supply_centers(p) for p in self.get_powers()}
        return sorted_by_key(centers)

    def _get_units_by_power(self) -> dict[Power, dict[Location, UnitType]]:
        """Return {power: {loc: unit_type}} nested mapping for all units."""
        power_units: dict[Power, dict[Location, UnitType]] = {}
        for power in self.get_powers():
            per_power: dict[Location, UnitType] = {}
            for unit_str in self._game.get_units(power):
                unit_type, loc = _split_unit(unit_str)
                per_power[loc] = unit_type
            power_units[power] = sorted_by_key(per_power)
        return sorted_by_key(power_units)

    def _get_dislodged_locations(self) -> list[Location]:
        """Return locations of units that are currently dislodged."""
        dislodged: list[Location] = []
        for power in self.get_powers():
            for unit_str in self._game.get_units(power):
                unit_type, loc = _split_unit(unit_str)
                if unit_type.startswith("*"):
                    dislodged.append(loc)
        return dislodged

    # ------------------------------------------------------------------
    # DTO Interface Constructors
    # ------------------------------------------------------------------

    def get_game_state(self) -> GameStateDTO:
        """Return a coarse snapshot of the entire game."""
        short_phase = self._game.get_current_phase()  # e.g. "S1901M"
        all_powers = self.get_powers()

        all_supply_center_locations = self.get_all_supply_centers()
        all_supply_center_counts = {k: len(v) for k, v in all_supply_center_locations.items()}

        all_unit_locations = sorted_by_key(self._get_units_by_power())

        return GameStateDTO(
            is_game_done=self._game.is_game_done,
            short_phase=short_phase,
            phase=str(self._game.phase),
            phase_type=self._game.phase_type,
            year=self.extract_year_from_phase(short_phase) or 0,
            all_powers=all_powers,
            all_supply_center_counts=all_supply_center_counts,
            all_supply_center_locations=all_supply_center_locations,
            all_unit_locations=all_unit_locations,
        )

    def get_power_view(self, power: Power) -> PowerViewDTO:
        """Return the board from *power*'s perspective."""
        all_possible: dict[Location, Orders] = sorted_by_key(self._game.get_all_possible_orders())
        orderable: tuple[Location, ...] = tuple(sorted(self._game.get_orderable_locations(power)))

        valid: dict[Location, tuple[str, ...]] = {
            loc: tuple(sorted(all_possible[loc])) for loc in orderable if loc in all_possible
        }
        valid = sorted_by_key(valid)

        # Parse unit list like ["A PAR", "F BRE"] into {"PAR": "A", "BRE": "F"}
        units_map: dict[Location, UnitType] = {}
        for unit_str in self._game.get_units(power):
            unit_type, loc = _split_unit(unit_str)
            units_map[loc] = unit_type
        units_map = sorted_by_key(units_map)

        # Home supply centres where *power* can build.
        # The underlying diplomacy engine stores them on the per-power object
        # under the ``homes`` attribute.
        centers = tuple(sorted(self._game.get_centers(power)))
        home_centers: tuple[Location, ...] = tuple(cast(list[Location], self._game.powers[power].homes))
        home_centers = tuple(sorted(set(home_centers) & set(centers)))  # Just owned home centers

        return PowerViewDTO(
            power=power,
            my_supply_center_count=len(centers),
            my_supply_center_locations=centers,
            my_home_supply_center_locations=home_centers,
            my_unit_locations=units_map,
            my_possible_orders_by_location=valid,
        )

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def set_orders(self, power: Power, orders: Orders) -> None:
        """Submit list of DATC order strings for *power*."""
        self._game.set_orders(power, orders)

    def process_turn(self) -> None:
        """Advance the game one phase."""
        self._game.process()

    def render_svg(self, *, incl_orders: bool = True, incl_abbrev: bool = True) -> str:
        """
        Return the current board as an SVG string.

        This wraps the upstream ``Renderer`` so higher-level code can decide
        *when* to capture frames without the engine having to maintain an
        internal buffer.
        """
        renderer: Callable[..., str] = Renderer(self._game).render
        return renderer(incl_orders=incl_orders, incl_abbrev=incl_abbrev)

    def save(self, file_path: str) -> None:
        """Write the current game to *file_path* in DATC JSON format."""
        export.to_saved_game_format(self._game, file_path, "w")
