# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
"""Typed, minimal façade over the `diplomacy` engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TypeVar

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

Orders = tuple[str, ...]  # immutable, external callers see a tuple

K = TypeVar("K")
V = TypeVar("V")


# ---------------------------------------------------------------------------
# Top‑level helpers (no class statics)
# ---------------------------------------------------------------------------


def sort_by_key[K, V](mapping: Mapping[K, V]) -> dict[K, V]:
    """Return a **new** dict sorted by key (ascending)."""
    return dict(sorted(mapping.items()))


def parse_unit(unit_str: str) -> tuple[UnitType, Location]:
    """Split `'A PAR'` → (`UnitType('A')`, `Location('PAR')`)."""
    unit_kind, loc = unit_str.split(" ", 1)
    return UnitType(unit_kind.strip("*")), Location(loc)  # `*A PAR` → dislodged


def year_from_short_phase(token: str) -> int | None:
    """Extract `1901` from `'S1901M'`."""
    return int(token[1:5]) if len(token) >= 5 and token[1:5].isdigit() else None


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class GameStateDTO(BaseModel):
    """Global, immutable game snapshot."""

    model_config = ConfigDict(strict=True, frozen=True)

    is_done: bool
    short_phase: str  # e.g. 'S1901M'
    phase: str  # e.g. 'SPRING 1901 MOVEMENT'
    phase_type: PhaseType
    year: int

    powers: tuple[Power, ...]
    supply_centers: dict[Power, tuple[Location, ...]]
    supply_center_counts: dict[Power, int]
    units: dict[Power, dict[Location, UnitType]]


class PowerViewDTO(BaseModel):
    """Snapshot from one power’s perspective."""

    model_config = ConfigDict(strict=True, frozen=True)

    power: Power
    supply_center_count: int
    supply_centers: tuple[Location, ...]
    home_supply_centers: tuple[Location, ...]
    units: dict[Location, UnitType]
    possible_orders: dict[Location, Orders]

    @property
    def flat_orders(self) -> Orders:
        """A flattened, deduplicated tuple of all legal orders."""
        return tuple(order for opts in self.possible_orders.values() for order in opts)


# ---------------------------------------------------------------------------
# Engine façade
# ---------------------------------------------------------------------------


class DiplomacyEngine:
    """Thin, typed wrapper around `diplomacy.Game`."""

    def __init__(self, *, rules: set[str] | None = None) -> None:
        """Initialize the diplomacy engine."""
        default_rules = {"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"}
        self._game: _RawGame = _RawGame(rules=rules or default_rules)

    # ---------------------------------------------------------------------
    # Public scalar getters
    # ---------------------------------------------------------------------

    @property
    def is_done(self) -> bool:
        """Return True if the game is over."""
        return self._game.is_game_done

    @property
    def short_phase(self) -> str:
        """Short phase string, e.g. 'S1901M'."""
        return self._game.get_current_phase()

    @property
    def phase(self) -> str:
        """Phase string, e.g. 'SPRING 1901 MOVEMENT'."""
        return str(self._game.phase)

    @property
    def phase_type(self) -> PhaseType:
        """Phase type, e.g. PhaseType.M."""
        return PhaseType(self._game.phase_type)

    @property
    def year(self) -> int:
        """Year, e.g. 1901."""
        return year_from_short_phase(self.short_phase) or 0

    # ---------------------------------------------------------------------
    # Public collection getters
    # ---------------------------------------------------------------------

    @property
    def powers(self) -> tuple[Power, ...]:
        """All powers in the game."""
        return tuple(sorted(Power(p) for p in self._game.powers))

    @property
    def supply_centers(self) -> dict[Power, tuple[Location, ...]]:
        """All supply centers in the game."""
        centers: dict[Power, tuple[Location, ...]] = {}
        for power in self.powers:
            centers[power] = tuple(sorted(Location(c) for c in self._game.get_centers(power)))
        return sort_by_key(centers)

    @property
    def supply_center_counts(self) -> dict[Power, int]:
        """Supply center counts for all powers."""
        return {p: len(locs) for p, locs in self.supply_centers.items()}

    @property
    def home_supply_centers(self) -> dict[Power, tuple[Location, ...]]:
        """All home supply centers for each power, sorted by power and location."""
        homes: dict[Power, tuple[Location, ...]] = {}
        for power in self.powers:
            locs = tuple(sorted(Location(h) for h in self._game.powers[power].homes))
            homes[power] = locs
        return sort_by_key(homes)

    @property
    def units(self) -> dict[Power, dict[Location, UnitType]]:
        """Units for all powers."""
        nested: dict[Power, dict[Location, UnitType]] = {}
        for power in self.powers:
            units_by_loc: dict[Location, UnitType] = {}
            for unit in self._game.get_units(power):
                kind, loc = parse_unit(unit)
                units_by_loc[loc] = kind
            nested[power] = sort_by_key(units_by_loc)
        return sort_by_key(nested)

    # ---------------------------------------------------------------------
    # DTO builders
    # ---------------------------------------------------------------------

    def game_state(self) -> GameStateDTO:
        """Return a coarse, type‑safe snapshot of the entire board."""
        return GameStateDTO(
            is_done=self.is_done,
            short_phase=self.short_phase,
            phase=self.phase,
            phase_type=self.phase_type,
            year=self.year,
            powers=self.powers,
            supply_centers=self.supply_centers,
            supply_center_counts=self.supply_center_counts,
            units=self.units,
        )

    def power_view(self, power: Power) -> PowerViewDTO:
        """Return a perspective snapshot for *power*."""
        # Possible orders
        raw_possible = sort_by_key(self._game.get_all_possible_orders())
        orderable = tuple(sorted(self._game.get_orderable_locations(power)))
        possible: dict[Location, Orders] = {
            Location(loc): tuple(sorted(raw_possible[loc])) for loc in orderable if loc in raw_possible
        }
        possible = sort_by_key(possible)

        # Units
        units_by_loc = self.units[power]

        # Home centres where *power* can build
        my_centers = self.supply_centers[power]
        all_home_centers = self.home_supply_centers[power]
        home_centers = tuple(loc for loc in all_home_centers if loc in my_centers)

        return PowerViewDTO(
            power=power,
            supply_center_count=len(my_centers),
            supply_centers=my_centers,
            home_supply_centers=home_centers,
            units=units_by_loc,
            possible_orders=possible,
        )

    # ---------------------------------------------------------------------
    # Engine I/O
    # ---------------------------------------------------------------------

    def set_orders(self, power: Power, orders: Orders) -> None:
        """Submit a tuple of DATC order strings for *power*."""
        self._game.set_orders(power, list(orders))  # engine expects list[str]

    def process_turn(self) -> None:
        """Advance the game by one phase."""
        self._game.process()

    def render_svg(self, *, incl_orders: bool = True, incl_abbrev: bool = True) -> str:
        """Return current board as an SVG string."""
        renderer: Callable[..., str] = Renderer(self._game).render
        return renderer(incl_orders=incl_orders, incl_abbrev=incl_abbrev)

    def save(self, file_path: str) -> None:
        """Write the game to *file_path* in DATC JSON format."""
        export.to_saved_game_format(self._game, file_path, "w")
