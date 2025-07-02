"""Minimal typed wrapper around the diplomacy package."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast, runtime_checkable

# Third-party diplomacy engine ------------------------------------------------
from diplomacy import Game as _RawGame
from diplomacy.engine.renderer import Renderer
from pydantic import BaseModel, ConfigDict, RootModel, field_validator

# Canonical token literals ---------------------------------------------------
from diplomacy_agents.literals import Location, PhaseType, Power, UnitType

# ---------------------------------------------------------------------------
# Generic order list model
# ---------------------------------------------------------------------------


class Orders(list[str]):
    """
    Business-logic list of DATC order strings.

    Subclassing :class:`list` gives downstream code first-class list semantics
    (indexing, slicing, mutating, ``isinstance(x, list)``, …) while still
    letting us wrap the value in a Pydantic ``RootModel`` for I/O boundaries.
    """


class OrdersModel(RootModel[list[str]]):
    """Pydantic wrapper providing validation / JSON-schema for :class:`Orders`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ---------------------------------------------------------------------------
# Typing for``diplomacy.Game`
# ---------------------------------------------------------------------------


@runtime_checkable
class _GameProtocol(Protocol):
    """Subset of the ``diplomacy.Game`` interface required by this wrapper."""

    # Public attributes -----------------------------------------------------
    powers: list[Power]
    phase_type: PhaseType
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
    """Immutable container with coarse game information."""

    model_config = ConfigDict(frozen=True)

    phase: str
    year: int
    is_game_done: bool
    powers: tuple[Power, ...]
    supply_centers: dict[Power, int]
    phase_type: PhaseType
    units_by_power: dict[Power, dict[Location, UnitType]]


class PowerViewDTO(BaseModel):
    """Perspective-specific snapshot for a single power."""

    model_config = ConfigDict(frozen=True)

    power: Power
    phase: str
    phase_type: PhaseType
    units: dict[Location, UnitType]
    supply_centers: tuple[Location, ...]
    orders_by_location: dict[Location, tuple[str, ...]]

    @property
    def orders_list(self) -> list[str]:
        """Return a single flat ``list`` containing all legal order strings."""
        return [order for opts in self.orders_by_location.values() for order in opts]

    def create_order_model(self) -> type[BaseModel]:
        """Return a RootModel validating that each entry is a legal order string."""
        allowed: set[str] = set(self.orders_list)

        class _OrdersRoot(OrdersModel):
            """Phase-specific order list ensuring only legal orders are used."""

            @field_validator("root")
            @classmethod
            def _check_orders(cls, v: Orders) -> Orders:
                illegal = [o for o in v if o not in allowed]
                if illegal:
                    raise ValueError(f"Illegal order(s) for {self.power}: {', '.join(illegal)}")
                return v

        _OrdersRoot.__name__ = f"OrdersList_{self.power}"
        max_show = 25
        sample = ", ".join(sorted(allowed)[:max_show])
        more = " ..." if len(allowed) > max_show else ""
        _OrdersRoot.__doc__ = (
            f"JSON array of DATC order strings for {self.power}. "
            f"Each element must be one of the legal orders in the current phase. "
            f"Example subset: {sample}{more}."
        )
        return _OrdersRoot


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

    def get_game_state(self) -> GameStateDTO:
        """Return a coarse snapshot of the entire game."""
        phase_token = self._game.get_current_phase()  # e.g. "S1901M"
        return GameStateDTO(
            phase=phase_token,
            year=int(phase_token[1:5]),
            is_game_done=self._game.is_game_done,
            powers=tuple(self._game.powers),
            supply_centers={p: len(self._game.get_centers(p)) for p in self._game.powers},
            phase_type=self._get_phase_type(),
            units_by_power=self._get_units_by_power(),
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
            # Dislodged units are prefixed with '*', e.g. "*A MUN". Strip such markers.  # TODO: REMOVE THIS?
            unit_type_clean = unit_type_str.lstrip("*?")  # '?' appears in some variants.
            unit_type = cast(UnitType, unit_type_clean)
            loc = cast(Location, loc_str)
            units_map[loc] = unit_type

        return PowerViewDTO(
            power=power,
            phase=self._game.get_current_phase(),
            phase_type=self._get_phase_type(),
            units=units_map,
            supply_centers=tuple(self._game.get_centers(power)),
            orders_by_location=valid,
        )

    def submit_orders(self, power: Power, orders: Orders) -> None:
        """Submit list of DATC order strings for *power*."""
        self._game.set_orders(power, orders)

    def process_turn(self) -> None:
        """Advance the game one phase."""
        self._game.process()

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
        # The underlying library uses either single letters *or* long words depending on context.
        mapping: dict[str, PhaseType] = {
            "M": "M",
            "MOVEMENT": "M",
            "R": "R",
            "RETREATS": "R",
            "A": "A",
            "ADJUSTMENT": "A",
            "ADJUSTMENTS": "A",
        }
        if pt_raw not in mapping:
            raise RuntimeError(f"Unknown phase type from engine: {pt_raw!r}")
        return mapping[pt_raw]

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
    "OrdersModel",
]
