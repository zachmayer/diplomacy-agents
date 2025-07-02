"""Minimal typed wrapper around the diplomacy package."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal, TypeVar, cast

# Third-party diplomacy engine ------------------------------------------------
from diplomacy import Game as _RawGame  # type: ignore[reportMissingTypeStubs]
from diplomacy.engine.renderer import Renderer  # type: ignore
from pydantic import BaseModel, ConfigDict, RootModel, field_validator
from pydantic_ai.models import KnownModelName

# Canonical token literals ---------------------------------------------------
from diplomacy_agents.literals import Location, PhaseType, Power, UnitType  # noqa: E402

# Third-party helpers ---------------------------------------------------------

# ---------------------------------------------------------------------------
# Generic order list model ---------------------------------------------------
# ---------------------------------------------------------------------------


class OrdersList(RootModel[list[str]]):
    """
    JSON array of DATC order strings.

    This *base* model imposes **no validation** beyond being a list of strings.
    Phase-/power-specific subclasses can inherit from it to add stricter
    constraints (see ``create_order_model``).
    """


# ---------------------------------------------------------------------------
# Simple data helpers --------------------------------------------------------
# ---------------------------------------------------------------------------


T_co = TypeVar("T_co", covariant=True)


def flatten_values[T_co](mapping: Mapping[Any, Iterable[T_co]]) -> list[T_co]:  # noqa: D401
    """
    Return a flat list containing every element from *mapping*'s values.

    Example:
    -------
    >>> flatten_values({"a": [1, 2], "b": [3]})
    [1, 2, 3]

    """
    flattened: list[T_co] = []
    for iterable in mapping.values():
        flattened.extend(iterable)
    return flattened


# ---------------------------------------------------------------------------
# Data-transfer objects (DTOs) -----------------------------------------------
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

    # Mapping each power to its own {location: unit_type} view – useful for
    # human-readable dumps where grouping by owner adds clarity.
    units_by_power: dict[Power, dict[Location, UnitType]]

    # Locations of units that were dislodged in the last movement phase and
    # must now retreat or be disbanded.  The information is aggregated for
    # convenience; ownership can be inferred by consulting the per-power
    # views if needed.
    dislodged_units: tuple[Location, ...]


class PowerViewDTO(BaseModel):
    """Perspective-specific snapshot for a single power."""

    model_config = ConfigDict(frozen=True)

    power: Power
    phase: str
    phase_type: PhaseType
    units: dict[Location, UnitType]
    supply_centers: tuple[Location, ...]
    orders_by_location: dict[Location, tuple[str, ...]]

    def create_order_model(self) -> type[BaseModel]:
        """Return a RootModel validating that each entry is a legal order string."""
        allowed: set[str] = set(flatten_values(self.orders_by_location))

        class _OrdersRoot(OrdersList):
            """Phase-specific order list ensuring only legal orders are used."""

            @field_validator("root")
            @classmethod
            def _check_orders(cls, v: list[str]) -> list[str]:
                illegal = [o for o in v if o not in allowed]
                if illegal:
                    raise ValueError(f"Illegal order(s) for {self.power}: {', '.join(illegal)}")
                return v

        _OrdersRoot.__name__ = f"OrdersList_{self.power}"
        # Docstring includes at most 25 sample orders for context.
        max_show = 25
        sample = ", ".join(sorted(allowed)[:max_show])
        more = " …" if len(allowed) > max_show else ""
        _OrdersRoot.__doc__ = (
            f"JSON array of DATC order strings for {self.power}. "
            f"Each element must be one of the legal orders in the current phase. "
            f"Example subset: {sample}{more}."
        )
        return _OrdersRoot


# ---------------------------------------------------------------------------
# Power→Model mapping --------------------------------------------------------
# ---------------------------------------------------------------------------


# Accept both LLM identifiers and baseline specifiers
AgentSpecName = KnownModelName | Literal["hold", "random"]


class PowerModelMap(BaseModel):
    """
    Validated mapping from each power to its LLM identifier.

    Each attribute corresponds to one of the seven standard powers and must be
    populated with a valid *pydantic-ai* ``KnownModelName`` **or** one of the
    built-in baseline specifiers ("hold" / "random").
    """

    model_config = ConfigDict(frozen=True)

    AUSTRIA: AgentSpecName
    ENGLAND: AgentSpecName
    FRANCE: AgentSpecName
    GERMANY: AgentSpecName
    ITALY: AgentSpecName
    RUSSIA: AgentSpecName
    TURKEY: AgentSpecName


# ---------------------------------------------------------------------------
# Engine façade --------------------------------------------------------------
# ---------------------------------------------------------------------------


class DiplomacyEngine:
    """Very thin wrapper exposing just the bits we need."""

    def __init__(self, *, rules: set[str] | None = None) -> None:
        """Create a new Diplomacy game instance."""
        # Use deadline-free rules by default so the driver controls phase ticks.
        default_rules: set[str] = {"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"}
        self._game: _RawGame = _RawGame(rules=rules or default_rules)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Public helpers ----------------------------------------------------
    # ------------------------------------------------------------------

    def get_game_state(self) -> GameStateDTO:
        """Return a coarse snapshot of the entire game."""
        phase_token = self._game.get_current_phase()  # e.g. "S1901M"
        return GameStateDTO(
            phase=phase_token,
            year=int(phase_token[1:5]),
            is_game_done=self._game.is_game_done,  # type: ignore[attr-defined]
            powers=tuple(self._game.powers),  # type: ignore[attr-defined]
            supply_centers={p: len(self._game.get_centers(p)) for p in self._game.powers},  # type: ignore[attr-defined]
            phase_type=self._get_phase_type(),
            units_by_power=self._get_units_by_power(),  # type: ignore[arg-type]
            dislodged_units=tuple(self._get_dislodged_locations()),
        )

    def get_power_view(self, power: Power) -> PowerViewDTO:
        """Return the board from *power*'s perspective."""
        all_possible: dict[str, list[str]] = self._game.get_all_possible_orders()  # type: ignore[attr-defined]
        orderable: tuple[str, ...] = tuple(self._game.get_orderable_locations(power))  # type: ignore[attr-defined]

        valid = {cast(Location, loc): tuple(all_possible[loc]) for loc in orderable if loc in all_possible}

        # Parse unit list like ["A PAR", "F BRE"] into {"PAR": "A", "BRE": "F"}
        units_map: dict[str, UnitType] = {}
        unit_strings = cast(list[str], self._game.get_units(power))  # type: ignore[attr-defined,arg-type]
        for unit_str in unit_strings:
            unit_type_str, loc_str = unit_str.split(" ", 1)
            # Dislodged units are prefixed with '*', e.g. "*A MUN". Strip such markers.
            unit_type_clean = unit_type_str.lstrip("*?")  # '?' appears in some variants.
            unit_type = cast(UnitType, unit_type_clean)  # type: ignore[reportUnnecessaryCast]
            loc = cast(Location, loc_str)  # type: ignore[reportUnnecessaryCast]
            units_map[loc] = unit_type

        return PowerViewDTO(
            power=power,
            phase=self._game.get_current_phase(),
            phase_type=self._get_phase_type(),
            units=units_map,  # type: ignore[arg-type]
            supply_centers=tuple(self._game.get_centers(power)),  # type: ignore[attr-defined]
            orders_by_location=valid,  # type: ignore[arg-type]
        )

    def submit_orders(self, power: Power, orders: list[str]) -> None:  # noqa: D401
        """Submit list of DATC order strings for *power*."""
        self._game.set_orders(power, orders)  # type: ignore[arg-type]

    def process_turn(self) -> None:  # noqa: D401
        """Advance the game one phase."""
        self._game.process()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Rendering helpers --------------------------------------------------
    # ------------------------------------------------------------------

    def svg_string(self, *, show_orders: bool = True) -> str:  # noqa: D401
        """
        Return an SVG snapshot of the current board state.

        Thin wrapper around ``diplomacy.utils.export.render_board_svg``.
        The upstream helper returns a plain SVG string generated entirely in
        Python – no external Cairo or other native libraries are needed.
        """
        renderer: Callable[..., str] = Renderer(self._game).render  # type: ignore[attr-defined]
        svg_xml: str = renderer(incl_orders=show_orders, output_format="svg")
        return svg_xml

    # ------------------------------------------------------------------
    # Internals ---------------------------------------------------------
    # ------------------------------------------------------------------

    def _get_phase_type(self) -> PhaseType:
        """Map diplomacy engine phase constant to single-letter code."""
        pt_raw: str = self._game.phase_type  # type: ignore[attr-defined]
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
    # Board-wide helpers -------------------------------------------------
    # ------------------------------------------------------------------

    def _get_units_by_power(self) -> dict[Power, dict[Location, UnitType]]:
        """Return {power: {loc: unit_type}} nested mapping for all units."""
        mp: dict[Power, dict[Location, UnitType]] = {}
        for power in self._game.powers:  # type: ignore[attr-defined]
            unit_strings = cast(list[str], self._game.get_units(power))  # type: ignore[arg-type]
            per_power: dict[Location, UnitType] = {}
            for unit_str in unit_strings:
                unit_type_str, loc_str = unit_str.split(" ", 1)
                unit_type_clean = unit_type_str.lstrip("*?")
                loc = cast(Location, loc_str)
                per_power[loc] = cast(UnitType, unit_type_clean)
            mp[cast(Power, power)] = per_power  # type: ignore[arg-type]
        return mp

    def _get_dislodged_locations(self) -> list[Location]:
        """Return locations of units that are currently dislodged."""
        dislodged: list[Location] = []
        for power in self._game.powers:  # type: ignore[attr-defined]
            unit_strings = cast(list[str], self._game.get_units(power))  # type: ignore[arg-type]
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
    "OrdersList",
    "flatten_values",
    "PowerModelMap",
]
