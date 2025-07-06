# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
"""Minimal typed wrapper around the diplomacy package."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, cast, runtime_checkable

from diplomacy import Game as _RawGame
from diplomacy.engine.message import GLOBAL, Message
from diplomacy.engine.renderer import Renderer
from diplomacy.utils import export
from pydantic import BaseModel, ConfigDict

from diplomacy_agents.literals import Location, PhaseType, Power, UnitType

# ---------------------------------------------------------------------------
# Typings
# ---------------------------------------------------------------------------


type Orders = list[str]  # TODO: should this be a tuple?

# Structural typing stub for the third-party ``Message`` class – we only rely on
# a handful of public attributes / methods, so a lightweight ``Protocol`` is
# sufficient and gives full static-type safety without wrapping the object.


@runtime_checkable
class MessageLike(Protocol):
    """Minimal subset of the third-party ``Message`` interface we consume."""

    sender: Power
    recipient: Power
    message: str
    time_sent: int | None

    def is_global(self) -> bool:  # noqa: D401
        """Return ``True`` if the message was addressed to everyone."""
        ...


# Covariant containers so we avoid the usual list/dict invariance headaches.
# Raw engine mapping used internally
type MessageMap = Mapping[int, MessageLike]

# Public-facing view uses *formatted strings*, not raw Message objects.
type MessageSeq = Sequence[str]


@runtime_checkable
class _GameProtocol(Protocol):
    """Subset of the ``diplomacy.Game`` interface required by this wrapper."""

    # Public attributes -----------------------------------------------------
    # Underlying engine maps power name to Power class instance. We don't use the Power class instance.
    powers: dict[Power, Any]
    phase_type: PhaseType  # e.g. "M"
    phase: str  # Long phase name, e.g. "SPRING 1901 MOVEMENT"
    is_game_done: bool  # True if the game is over
    messages: MessageMap

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

    # Helper for visibility filtering of messages.
    def filter_messages(
        self,
        messages: MessageMap,
        game_role: Power,
        timestamp_from: int | None = None,
        timestamp_to: int | None = None,
    ) -> MessageMap: ...


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


class PowerViewDTO(BaseModel):
    """Perspective-specific snapshot for *one* power."""

    model_config = ConfigDict(strict=True, frozen=True, arbitrary_types_allowed=False)

    # Scalars -----------------------------------------------------------------
    power: Power

    # Collections -------------------------------------------------------------
    # TODO: should these be "your" instead of "my"?
    my_supply_center_count: int
    my_unit_locations: dict[Location, UnitType]
    my_home_supply_center_locations: tuple[Location, ...]
    my_supply_center_locations: tuple[Location, ...]
    my_orders_by_location: dict[Location, tuple[str, ...]]
    press_messages: tuple[str, ...]

    @property
    def orders_list(self) -> Orders:
        """Return a single flat ``list`` containing all legal order strings."""
        return [order for opts in self.my_orders_by_location.values() for order in opts]


# ---------------------------------------------------------------------------
# Engine façade
# ---------------------------------------------------------------------------


def format_message(m: MessageLike) -> str:
    """Return human-readable ``sender → recipient: text`` string."""
    recipient = "ALL" if m.is_global() else m.recipient
    # Use Unicode arrow with surrounding spaces for clarity.
    return f"{m.sender} → {recipient}: {m.message}"


def _split_unit(unit_str: str) -> tuple[UnitType, Location]:
    """Parse a unit string like 'A PAR' into typed components."""
    unit_type_str, loc_str = unit_str.split(" ", 1)
    return cast(UnitType, unit_type_str), cast(Location, loc_str)


class DiplomacyEngine:
    """Very thin wrapper exposing just the bits we need."""

    def __init__(self, *, rules: set[str] | None = None) -> None:
        """Create a new Diplomacy game instance."""
        default_rules: set[str] = {"NO_DEADLINE", "ALWAYS_WAIT", "CIVIL_DISORDER"}
        raw_game = _RawGame(rules=rules or default_rules)
        self._game: _GameProtocol = cast(_GameProtocol, raw_game)

    def get_game_state(self) -> GameStateDTO:
        """Return a coarse snapshot of the entire game."""
        phase_token = self._game.get_current_phase()  # e.g. "S1901M"

        return GameStateDTO(
            is_game_done=self._game.is_game_done,
            phase=phase_token,
            phase_long=str(self._game.phase),
            phase_type=self._game.phase_type,
            year=self._extract_year_from_phase(phase_token) or 0,
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
        for unit_str in self._game.get_units(power):
            unit_type, loc = _split_unit(unit_str)
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
            press_messages=tuple(self.get_current_phase_messages(power)),
        )

    def submit_orders(self, power: Power, orders: Orders) -> None:
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

    # --------------------------------------------------------------
    # Public press -------------------------------------------------
    # --------------------------------------------------------------

    def add_message(self, sender: Power, message: str, recipient: Power | None = None) -> None:
        """Record a public (recipient=None) or private 1→1 message in the engine."""
        msg = Message(
            phase=self._game.current_short_phase,
            sender=sender,
            recipient=GLOBAL if recipient is None else recipient,
            message=message,
        )

        self._game.add_message(msg)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_units_by_power(self) -> dict[Power, dict[Location, UnitType]]:
        """Return {power: {loc: unit_type}} nested mapping for all units."""
        mp: dict[Power, dict[Location, UnitType]] = {}
        for power in self._game.powers:
            per_power: dict[Location, UnitType] = {}
            for unit_str in self._game.get_units(power):
                unit_type, loc = _split_unit(unit_str)
                per_power[loc] = unit_type
            mp[power] = per_power
        return mp

    def _get_dislodged_locations(self) -> list[Location]:
        """Return locations of units that are currently dislodged."""
        dislodged: list[Location] = []
        for power in self._game.powers:
            for unit_str in self._game.get_units(power):
                unit_type, loc = _split_unit(unit_str)
                if unit_type.startswith("*"):
                    dislodged.append(loc)
        return dislodged

    def _extract_year_from_phase(self, phase_token: str) -> int | None:
        """Return the four-digit year component from a phase token like "S1901M"."""
        if len(phase_token) >= 5 and phase_token[1:5].isdigit():
            return int(phase_token[1:5])
        return None

    def get_current_phase_messages(self, power: Power) -> list[str]:
        """
        Return chronological messages visible to *power* from a single phase.

        The upstream ``diplomacy`` engine keeps *current-phase* messages in
        ``self._game.messages`` and archives completed phases in
        ``self._game.messages_history``

        Parameters
        ----------
        power
            The in-game power whose perspective we take when filtering visibility.

        """
        filtered: MessageMap = self._game.filter_messages(  # type: ignore[attr-defined]
            self._game.messages,
            game_role=power,
        )

        # ``time_sent`` may be ``None`` during early tests; treat as 0.
        messages_sorted = sorted(filtered.values(), key=lambda m: (m.time_sent or 0))
        return [format_message(m) for m in messages_sorted]


__all__ = [
    "DiplomacyEngine",
    "GameStateDTO",
    "PowerViewDTO",
    "Power",
    "Location",
    "UnitType",
    "PhaseType",
    "Orders",
    "MessageLike",
    "MessageSeq",
    "MessageMap",
    "format_message",
]
