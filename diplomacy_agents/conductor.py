"""
Event-driven conductor and RPC layer for Diplomacy-Agents.

This module owns the *push*-based architecture that wakes each agent every
time something interesting happens (new press, board update, phase change).
All casting to and from the untyped *diplomacy* engine remains inside
``engine.py`` – this file is pure application logic and **fully typed**.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from diplomacy_agents.engine import Game, create_model_message, legal_orders, send_press, snapshot_board
from diplomacy_agents.literals import Location, Power, PressRecipient
from diplomacy_agents.models import BoardState, PressMessage
from diplomacy_agents.types import Order

__all__ = [
    "Event",
    "GameManager",
    "GameRPC",
    "driver",
]

# Type-only imports ---------------------------------------------------------

if TYPE_CHECKING:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# Event model ----------------------------------------------------------------
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Event:  # noqa: D101 (concise dataclass)
    kind: Literal["PRESS", "BOARD_STATE", "PHASE_CHANGE", "SYSTEM"]
    payload: dict[str, Any]
    sender: str  # "SYSTEM" | Power
    recipient: str  # "ALL" | Power
    ts: float


# ---------------------------------------------------------------------------
# Game RPC – thin helper passed to agents ------------------------------------
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class GameRPC:  # noqa: D101
    power: Power
    gm: GameManager

    # Synchronous helpers --------------------------------------------------

    def board_state(self) -> BoardState:  # noqa: D401
        """Return the latest board snapshot."""
        return snapshot_board(self.gm.game)

    def my_possible_orders(self) -> dict[Location, list[Order]]:  # noqa: D401
        """Legal orders for *self.power* right now."""
        return legal_orders(self.gm.game, self.power)

    # Async RPCs -----------------------------------------------------------

    async def send_press(self, to: PressRecipient, text: str) -> None:  # noqa: D401
        """Send a press message to *to*."""
        await self.gm.handle_press(self.power, to, text)

    async def submit_orders(self, orders: list[Order]) -> bool:  # noqa: D401
        """Submit orders for *self.power*; returns ``True`` if accepted."""
        return await self.gm.handle_orders(self.power, orders)


# ---------------------------------------------------------------------------
# GameManager – core event loop ---------------------------------------------
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


class GameManager:  # noqa: D101
    def __init__(self, *, seed: int = 42) -> None:
        """Initialize new game and spin up async phase loop."""
        # Ensure at least basic logging configured if the application hasn't.
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

        random.seed(seed)
        self.game: Game = Game(rules={"NO_DEADLINE", "ALWAYS_WAIT", "CD_DUMMIES"})

        # Async inbox per power; every event is pushed to every relevant inbox.
        self.inboxes: Mapping[Power, asyncio.Queue[Event]] = {p: asyncio.Queue() for p in self.game.powers}

        # Track which powers have submitted orders this phase.
        self._orders_buf: dict[Power, list[Order]] = {}

        # Kick off the main phase-processing loop.
        asyncio.create_task(self._main_loop())

    # ------------------------------------------------------------------
    # Agent-facing RPCs -------------------------------------------------
    # ------------------------------------------------------------------

    async def handle_press(self, sender: Power, to: PressRecipient, text: str) -> None:
        """Validate + store press, then broadcast event."""
        press = PressMessage(to=to, text=text)
        logger.info("PRESS %s → %s: %s", sender, to, text)
        send_press(self.game, sender, press)  # writes into engine log
        await self._broadcast("PRESS", press.model_dump(), sender, str(to))

    async def handle_orders(self, pwr: Power, orders: list[Order]) -> bool:
        """Validate and buffer orders; broadcast status event."""
        legal_set = {o for loc_orders in legal_orders(self.game, pwr).values() for o in loc_orders}
        if not all(o in legal_set for o in orders):
            logger.info("ORDERS_REJECTED %s invalid=%s", pwr, orders)
            return False

        # Use engine helper instead of raw access
        self.game.set_orders(pwr, orders)
        logger.info("ORDERS_ACCEPTED %s: %s", pwr, orders)
        self._orders_buf[pwr] = orders
        await self._broadcast(
            "SYSTEM",
            {"status": "ORDERS_SUBMITTED", "power": pwr},
            "SYSTEM",
            "ALL",
        )
        return True

    # ------------------------------------------------------------------
    # Internal helpers --------------------------------------------------
    # ------------------------------------------------------------------

    async def _broadcast(
        self,
        kind: Literal["PRESS", "BOARD_STATE", "PHASE_CHANGE", "SYSTEM"],
        payload: dict[str, Any],
        sender: str,
        recipient: str | Literal["ALL"],
    ) -> None:
        """Push *Event* to all matching inboxes.*."""
        ev = Event(kind, payload, sender, recipient, time.time())
        logger.debug("BROADCAST %s from %s to %s", kind, sender, recipient)
        if recipient == "ALL":
            for power in self.inboxes:
                self.inboxes[power].put_nowait(ev)
        else:
            # recipient must be a Power when not "ALL"
            for power in self.inboxes:
                if power == recipient:
                    self.inboxes[power].put_nowait(ev)
                    break

    async def _main_loop(self) -> None:  # noqa: C901 (simple but long)
        """Phase-processing loop – runs until game end."""
        # Broadcast initial board.
        await self._broadcast(
            "BOARD_STATE",
            snapshot_board(self.game).model_dump(),
            "SYSTEM",
            "ALL",
        )

        while not self.game.is_game_done:
            # Wait until every power has submitted at least once.
            while len(self._orders_buf) < len(self.game.powers):
                await asyncio.sleep(0.1)

            # Clear buffer for next phase.
            self._orders_buf.clear()

            # Process phase, generate new board.
            logger.info("PROCESSING phase %s", self.game.get_current_phase())
            self.game.process()
            logger.info("ADVANCED to phase %s", self.game.get_current_phase())

            # Broadcast new board + phase change.
            await self._broadcast(
                "BOARD_STATE",
                snapshot_board(self.game).model_dump(),
                "SYSTEM",
                "ALL",
            )
            await self._broadcast(
                "PHASE_CHANGE",
                {"phase": self.game.get_current_phase()},
                "SYSTEM",
                "ALL",
            )


# ---------------------------------------------------------------------------
# Agent driver ---------------------------------------------------------------
# ---------------------------------------------------------------------------


def _to_chat(ev: Event, me: Power) -> object:  # noqa: D401, ANN401
    """Map *Event* → ModelRequest for pydantic_ai."""
    if ev.kind == "PRESS":
        role = "user" if ev.recipient == me else "assistant"
        content = f"{ev.sender}→{ev.recipient}: {ev.payload['text']}"
    elif ev.kind == "BOARD_STATE":
        phase_info = ev.payload.get("phase") or "?"
        content = f"BOARD_STATE {phase_info}: {json.dumps(ev.payload)}"
        role = "system"
    elif ev.kind == "PHASE_CHANGE":
        content = f"PHASE_CHANGE: {ev.payload['phase']}"
        role = "system"
    else:  # SYSTEM
        content = json.dumps(ev.payload)
        role = "system"

    return create_model_message(role, content)


async def driver(
    agent: Any,  # noqa: ANN401 – pydantic_ai.Agent runtime object
    inbox: asyncio.Queue[Event],
    rpc: GameRPC,
) -> None:  # noqa: D401
    """Forever task that consumes *inbox* events and wakes *agent*."""
    history: list[Any] = []
    logger.info("Driver started for %s", rpc.power)
    while True:
        ev = await inbox.get()
        logger.debug("INBOX %s received %s event", rpc.power, ev.kind)
        history.append(_to_chat(ev, rpc.power))
        agent_any: Any = agent
        run_fn: Any = agent_any.run
        await run_fn("NEW_EVENT", deps=rpc, message_history=history)
        logger.debug("Agent %s run completed", rpc.power)
