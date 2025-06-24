"""
Typed wrappers around the untyped *diplomacy* engine.

This is **the single file** that touches the third-party library directly.  All
casts and ``# type: ignore`` comments live here so the rest of the codebase can
remain perfectly type-checked under *pyright --strict*.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast, get_args

import drawsvg as draw  # type: ignore[reportUnknownVariableType]
from diplomacy import Game as _RawGame  # type: ignore[reportMissingTypeStubs]
from diplomacy.engine.message import Message  # type: ignore[reportMissingTypeStubs]
from diplomacy.engine.renderer import Renderer
from diplomacy.utils.export import to_saved_game_format  # type: ignore[reportUnknownVariableType]

from diplomacy_agents.literals import Location, Power, UnitType
from diplomacy_agents.models import BoardState, PowerState, PressMessage
from diplomacy_agents.types import Order

__all__ = [
    "Engine",  # adapter class
    "centers",
    "units",
    "all_possible_orders",
    "snapshot_board",
    "legal_orders",
    "submit_orders",
    "send_press",
    "press_history",
    "broadcast_board_state",
    "export_datc",
    "to_power",
    "Game",
    "svg_string",
    "generate_svg_animation",
    "ensure_str_list",
]

# ---------------------------------------------------------------------------
# Safe wrapper around diplomacy.engine.Game ---------------------------------
# ---------------------------------------------------------------------------


class Game:
    """
    Typed façade over ``diplomacy.Game``.

    Only exposes the minimal API surface required by the project – more can be
    added as needed, **but keep all casts inside this module**.
    """

    def __init__(self, *, rules: set[str] | None = None) -> None:
        """Initialize the Game wrapper with optional rule set."""
        self._inner = _RawGame(rules=rules)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Basic properties & helpers ---------------------------------------
    # ------------------------------------------------------------------

    @property
    def powers(self) -> tuple[Power, ...]:
        """Return participating powers as project literals."""
        return tuple(cast(Power, p) for p in self._inner.powers)  # type: ignore[attr-defined]

    @property
    def is_game_done(self) -> bool:
        """Return True if the game has ended."""
        return self._inner.is_game_done  # type: ignore[attr-defined]

    def get_current_phase(self) -> str:
        """Return the current game phase."""
        return self._inner.get_current_phase()  # type: ignore[attr-defined]

    def process(self) -> None:
        """Process the current phase and advance the game state."""
        self._inner.process()  # type: ignore[attr-defined]

    @property
    def all_locations(self) -> list[str]:
        """Return all location tokens present on the map (including coast variants)."""
        # The underlying diplomacy engine stores location objects that stringify to the
        # standard DATC tokens (e.g. "PAR", "SPA/NC").  Preserve that representation.
        return [str(loc) for loc in self._inner.map.locs]  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Orders & press helpers -------------------------------------------
    # ------------------------------------------------------------------

    def get_all_possible_orders(self) -> dict[Location, list[Order]]:
        """Return all possible orders for all units on the board."""
        raw: dict[str, list[str]] = self._inner.get_all_possible_orders()  # type: ignore[attr-defined]
        return {cast(Location, loc): orders for loc, orders in raw.items()}

    def get_orderable_locations(self, power: Power) -> tuple[Location, ...]:
        """Return locations where the given power can issue orders."""
        raw: list[str] = self._inner.get_orderable_locations(power)  # type: ignore[attr-defined]
        return tuple(cast(Location, loc) for loc in raw)

    def set_orders(self, power: Power, orders: list[Order]) -> None:
        """Set orders for the given power."""
        self._inner.set_orders(power, orders)  # type: ignore[attr-defined]

    @property
    def messages(self) -> Mapping[int, Message]:
        """Return all messages in the game."""
        return self._inner.messages  # type: ignore[attr-defined,return-value]

    def add_message(self, msg: Message) -> None:
        """Add a message to the game log."""
        self._inner.add_message(msg)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Engine interop ----------------------------------------------------
    # ------------------------------------------------------------------

    @property
    def raw(self) -> _RawGame:
        """Expose the underlying *diplomacy* object for rare escape hatches."""
        return self._inner


# ---------------------------------------------------------------------------
# Internal helper casts ------------------------------------------------------
# ---------------------------------------------------------------------------


def centers(game: Game, pwr: Power) -> tuple[Location, ...]:
    """Typed wrapper around ``Game.raw.get_centers``."""
    raw: list[str] = game.raw.get_centers(pwr)  # type: ignore[attr-defined]
    return tuple(cast(Location, loc) for loc in raw)


def units(game: Game, pwr: Power) -> dict[Location, UnitType]:
    """Typed wrapper around ``Game.raw.get_units``."""
    raw: list[str] = game.raw.get_units(pwr)  # type: ignore[attr-defined]

    # Parse list of unit strings like ['A BUD', 'F TRI']
    result: dict[Location, UnitType] = {}
    for unit_str in raw:
        parts: list[str] = unit_str.split(" ", 1)  # Split into unit type and location
        if len(parts) == 2:
            unit_type: str = parts[0]
            location: str = parts[1]
            result[cast(Location, location)] = cast(UnitType, unit_type)
    return result


# ---------------------------------------------------------------------------
# Orders helper exposed for agents ------------------------------------------
# ---------------------------------------------------------------------------


def all_possible_orders(game: Game) -> dict[Location, list[Order]]:
    """Return *every* legal order for *every* unit on the board."""
    raw: dict[str, list[str]] = game.get_all_possible_orders()  # type: ignore[attr-defined]
    return {cast(Location, loc): orders for loc, orders in raw.items()}


# ---------------------------------------------------------------------------
# Public, typed helpers ------------------------------------------------------
# ---------------------------------------------------------------------------


def snapshot_board(game: Game) -> BoardState:
    """Return a fully typed snapshot of the current board."""
    powers_map: dict[Power, PowerState] = {
        p: PowerState(centers=centers(game, p), units=units(game, p)) for p in game.powers
    }
    return BoardState(powers=powers_map)


def legal_orders(game: Game, power: Power) -> dict[Location, list[Order]]:
    """Return legal orders for *power* this phase."""
    raw_map = game.get_all_possible_orders()
    orderable = game.get_orderable_locations(power)
    return {loc: raw_map[loc] for loc in orderable}


def submit_orders(game: Game, power: Power, orders: list[Order]) -> bool:
    """Submit *orders* for *power*; returns ``True`` if accepted."""
    legal_set = {o for loc_orders in legal_orders(game, power).values() for o in loc_orders}
    if not all(o in legal_set for o in orders):
        return False
    game.set_orders(power, orders)
    return True


def send_press(game: Game, sender: Power, press: PressMessage) -> None:
    """Append *press* to the game log."""
    msg = Message(
        sender=sender,  # type: ignore[arg-type]
        recipient=press.to,  # type: ignore[arg-type]
        message=press.text,
        phase=game.get_current_phase(),
    )
    game.add_message(msg)


def press_history(game: Game, power: Power, limit: int = 200) -> list[dict[str, Any]]:
    """Return last *limit* messages involving *power* as raw ``dict`` representations."""
    raw_msgs = list(game.messages.values())
    filtered = [m for m in reversed(raw_msgs) if m.sender == power or m.recipient in (power, "ALL")][:limit]
    # Message objects use __slots__, so build dict manually
    return [
        {
            "sender": m.sender,
            "recipient": m.recipient,
            "message": m.message,
            "phase": m.phase,
        }
        for m in filtered
    ]


# ---------------------------------------------------------------------------
# System helpers -------------------------------------------------------------
# ---------------------------------------------------------------------------


def broadcast_board_state(game: Game, board_state: BoardState) -> None:
    """Broadcast *board_state* to all powers via a SYSTEM message."""
    msg = Message(
        sender="SYSTEM",  # type: ignore[arg-type]
        recipient="ALL",  # type: ignore[arg-type]
        message=str(board_state.model_dump_json()),
        phase=game.get_current_phase(),
    )
    game.add_message(msg)


def export_datc(game: Game, path: Path) -> None:
    """Write game record in DATC save-file format."""
    to_saved_game_format(game.raw, output_path=str(path))


# ---------------------------------------------------------------------------
# SVG string helper (in-memory) ---------------------------------------------
# ---------------------------------------------------------------------------


def svg_string(game: Game) -> str:  # noqa: D401
    """Render *game* position and return raw SVG text."""
    renderer = Renderer(game.raw)  # type: ignore[arg-type]
    # Include orders and province abbreviations in the SVG.
    return str(renderer.render(incl_orders=True, incl_abbrev=True))  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# SVG animation helper – in-memory frames -----------------------------------
# ---------------------------------------------------------------------------


def generate_svg_animation(frames: list[str], out_file: Path, size: tuple[int, int] = (1200, 850)) -> None:  # noqa: D401
    """
    Write *out_file* animated SVG built from *frames* SVG strings.

    Each frame is shown for one second.
    """
    if not frames:
        return

    duration = len(frames)
    # drawsvg is untyped – cast objects to *Any* before calling dynamic methods
    d_any: Any = draw.Drawing(
        *size,
        animation_config=cast(Any, draw.types).SyncedAnimationConfig(duration=duration),  # type: ignore[attr-defined]
    )

    for i, svg_text in enumerate(frames):
        img_any: Any = draw.Image(  # type: ignore[no-any-call]
            0,
            0,
            *size,
            data=svg_text.encode("utf-8"),
            mime_type="image/svg+xml",
        )

        img_any.add_key_frame(i, opacity=0)
        img_any.add_key_frame(i + 0.01, opacity=1)
        img_any.add_key_frame(i + 1, opacity=1)
        img_any.add_key_frame(i + 1.01, opacity=0)

        d_any.append(img_any)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    d_any.save_svg(out_file)


# ---------------------------------------------------------------------------
# Utility --------------------------------------------------------------------
# ---------------------------------------------------------------------------


def to_power(token: str) -> Power:
    """Validate *token* and return it as a typed ``Power`` literal."""
    if token not in get_args(Power):
        raise ValueError(f"Unknown power '{token}'.")
    return cast(Power, token)


# Public alias – preferred import name per API spec
Engine = Game

# ---------------------------------------------------------------------------
# Typing helper -------------------------------------------------------------
# ---------------------------------------------------------------------------


def ensure_str_list(val: list[object]) -> list[str]:  # noqa: D401
    """Runtime-assert and cast *val* to ``list[str]`` (engine escape hatch)."""
    assert all(isinstance(x, str) for x in val), "Expected list[str]"
    return cast(list[str], val)
