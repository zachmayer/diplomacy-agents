"""Minimal typed wrapper around the diplomacy package."""

from __future__ import annotations

from typing import Literal, cast

# Third-party diplomacy engine ------------------------------------------------
from diplomacy import Game as _RawGame  # type: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, ConfigDict, RootModel, field_validator

# ---------------------------------------------------------------------------
# Canonical literals ---------------------------------------------------------
# ---------------------------------------------------------------------------

Power = Literal[
    "AUSTRIA",
    "ENGLAND",
    "FRANCE",
    "GERMANY",
    "ITALY",
    "RUSSIA",
    "TURKEY",
]

Location = str  # province token such as "PAR" or "SPA/NC"
UnitType = Literal["A", "F"]  # army / fleet – *build* variants ignored for simplicity

PhaseType = Literal["M", "R", "A"]  # Movement / Retreats / Adjustments

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


class PowerViewDTO(BaseModel):
    """Perspective-specific snapshot for a single power."""

    model_config = ConfigDict(frozen=True)

    power: Power
    phase: str
    phase_type: PhaseType
    units: dict[Location, UnitType]
    supply_centers: tuple[Location, ...]
    valid_orders: dict[Location, tuple[str, ...]]
    allowed_orders: tuple[str, ...]

    def create_order_model(self) -> type[BaseModel]:
        """Return a RootModel validating that each entry is a legal order string."""
        allowed: set[str] = set(self.allowed_orders)

        class _OrdersRoot(RootModel[list[str]]):
            """Pydantic root model ensuring all orders are legal for the phase."""

            @field_validator("root")
            @classmethod
            def _check_orders(cls, v: list[str]) -> list[str]:
                illegal = [o for o in v if o not in allowed]
                if illegal:
                    raise ValueError(f"Illegal order(s) for {self.power}: {', '.join(illegal)}")
                return v

        _OrdersRoot.__name__ = f"OrdersList_{self.power}"
        # Provide a helpful, power- and phase-specific docstring so that higher-level
        # tooling such as *pydantic-ai* can surface the constraint set to an LLM.
        # Keep it short – we don't want to flood the prompt with dozens of orders on
        # large boards but enough to give context.
        max_show = 25  # arbitrary cut-off to avoid huge strings
        sample = ", ".join(sorted(allowed)[:max_show])
        more = " …" if len(allowed) > max_show else ""
        _OrdersRoot.__doc__ = (
            f"JSON array of DATC order strings for {self.power}. "
            f"Each element must be one of the legal orders in the current phase. "
            f"Example subset: {sample}{more}."
        )
        return _OrdersRoot


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
        )

    def get_power_view(self, power: Power) -> PowerViewDTO:
        """Return the board from *power*'s perspective."""
        all_possible: dict[str, list[str]] = self._game.get_all_possible_orders()  # type: ignore[attr-defined]
        orderable: tuple[str, ...] = tuple(self._game.get_orderable_locations(power))  # type: ignore[attr-defined]

        valid = {loc: tuple(all_possible[loc]) for loc in orderable if loc in all_possible}

        # Parse unit list like ["A PAR", "F BRE"] into {"PAR": "A", "BRE": "F"}
        units_map: dict[str, UnitType] = {}
        unit_strings = cast(list[str], self._game.get_units(power))  # type: ignore[attr-defined,arg-type]
        for unit_str in unit_strings:
            unit_type_str, loc_str = unit_str.split(" ", 1)
            unit_type = cast(UnitType, unit_type_str)  # type: ignore[reportUnnecessaryCast]
            loc = cast(Location, loc_str)  # type: ignore[reportUnnecessaryCast]
            units_map[loc] = unit_type

        return PowerViewDTO(
            power=power,
            phase=self._game.get_current_phase(),
            phase_type=self._get_phase_type(),
            units=units_map,  # type: ignore[arg-type]
            supply_centers=tuple(self._game.get_centers(power)),  # type: ignore[attr-defined]
            valid_orders=valid,  # type: ignore[arg-type]
            allowed_orders=tuple({o for opts in valid.values() for o in opts}),
        )

    def submit_orders(self, power: Power, orders: list[str]) -> None:  # noqa: D401
        """Submit list of DATC order strings for *power*."""
        self._game.set_orders(power, orders)  # type: ignore[arg-type]

    def process_turn(self) -> None:  # noqa: D401
        """Advance the game one phase."""
        self._game.process()  # type: ignore[attr-defined]

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


__all__ = [
    "DiplomacyEngine",
    "GameStateDTO",
    "PowerViewDTO",
    "Power",
    "Location",
    "UnitType",
    "PhaseType",
]
