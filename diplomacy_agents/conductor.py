"""
Event-driven conductor and RPC layer for Diplomacy-Agents.

This module owns the *push*-based architecture that wakes each agent every
time something interesting happens (new press, board update, phase change).
All casting to and from the untyped *diplomacy* engine remains inside
``engine.py`` – this file is pure application logic and **fully typed**.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic_ai.messages import (
    ModelRequest,
    SystemPromptPart,
    ToolCallPart,
)

from diplomacy_agents.engine import Game, legal_orders, send_press, snapshot_board
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
            {"status": "ORDERS_SUBMITTED", "power": pwr, "orders": orders},
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
        # Kick off with an initial PHASE_CHANGE message that includes the
        # starting board state so agents have one canonical system snapshot.
        await self._broadcast(
            "PHASE_CHANGE",
            {
                "phase": self.game.get_current_phase(),
                "board": snapshot_board(self.game).model_dump(),
            },
            "SYSTEM",
            "ALL",
        )

        while not self.game.is_game_done:
            # Wait until every power has submitted at least once.
            wait_start = time.monotonic()
            last_log = wait_start
            while len(self._orders_buf) < len(self.game.powers):
                await asyncio.sleep(0.1)
                now = time.monotonic()
                if now - last_log >= 10:
                    logger.info(
                        "WAITING_FOR_ORDERS %d/%d submitted (%.0fs elapsed)",
                        len(self._orders_buf),
                        len(self.game.powers),
                        now - wait_start,
                    )
                    # Nudge agents with a system event so they wake up again.
                    await self._broadcast(
                        "SYSTEM",
                        {
                            "status": "AWAITING_ORDERS",
                            "submitted": len(self._orders_buf),
                            "total": len(self.game.powers),
                            "elapsed": int(now - wait_start),
                        },
                        "SYSTEM",
                        "ALL",
                    )
                    last_log = now

            # Clear buffer for next phase.
            self._orders_buf.clear()

            # Process phase, generate new board.
            logger.info("PROCESSING phase %s", self.game.get_current_phase())
            self.game.process()
            logger.info("ADVANCED to phase %s", self.game.get_current_phase())

            # Broadcast phase change including fresh board snapshot.
            await self._broadcast(
                "PHASE_CHANGE",
                {
                    "phase": self.game.get_current_phase(),
                    "board": snapshot_board(self.game).model_dump(),
                },
                "SYSTEM",
                "ALL",
            )


# ---------------------------------------------------------------------------
# Agent driver ---------------------------------------------------------------
# ---------------------------------------------------------------------------


def _event_to_message(ev: Event, me: Power) -> ModelRequest | None:  # noqa: D401, ANN001
    """
    Convert *Event* into a ModelRequest for the agent run chain.

    Mapping rules (per pydantic-ai conventions):
    1.  Messages *originated by **me*** – already present in history via the
        model's **assistant** response; skip to avoid duplicates.
    2.  Messages from **other powers** or the conductor – encoded as
        *system* prompts so the agent perceives them as external context.
    3.  Phase changes and explicit system notifications remain system prompts.
    """
    if ev.kind == "PRESS":
        # Skip own messages – they were already added to history as the model's response.
        if ev.sender == me:
            return None

        # All external press is treated as a system message for the receiving agent.
        content = f"{ev.sender}→{ev.recipient}: {ev.payload['text']}"
        return ModelRequest(parts=[SystemPromptPart(content=content)])

    if ev.kind == "SYSTEM":
        # Show own order submissions.
        if ev.payload.get("status") == "ORDERS_SUBMITTED" and ev.payload["power"] == me:
            joined = ", ".join(ev.payload["orders"])
            return ModelRequest(parts=[SystemPromptPart(content=f"YOUR_ORDERS: {joined}")])
        # other system nudges ignored.
        return None

    if ev.kind == "PHASE_CHANGE":
        phase = ev.payload["phase"]
        board_json = ev.payload["board"]
        content = f"PHASE_CHANGE {phase}\nBOARD_STATE {board_json}"
        return ModelRequest(parts=[SystemPromptPart(content=content)])

    # Ignore BOARD_STATE events (redundant) after refactor.
    return None


async def driver(
    agent: Any,  # noqa: ANN401 – pydantic_ai.Agent runtime object
    inbox: asyncio.Queue[Event],
    rpc: GameRPC,
) -> None:  # noqa: D401
    """Forever task that consumes *inbox* events and wakes *agent*."""
    from pydantic_ai.messages import ModelMessage

    history: list[ModelMessage] = []
    logger.info("Driver started for %s", rpc.power)
    while True:
        ev = await inbox.get()
        logger.debug("INBOX %s received %s event", rpc.power, ev.kind)
        msg = _event_to_message(ev, rpc.power)
        if msg is not None:
            history.append(msg)

        agent_any: Any = agent
        run_fn: Any = agent_any.run

        result = await run_fn(None, deps=rpc, message_history=history)

        # Extend history with model's new messages, skipping tool call/response
        for msg in result.new_messages():
            # Skip tool call requests (contain ToolCallPart) and tool responses (role == 'tool').
            if any(isinstance(p, ToolCallPart) for p in msg.parts):
                continue

            # Guard against pydantic-ai generated tool response messages which have role="tool".
            # These should not be replayed in future requests as they break OpenAI's role ordering rules.
            if getattr(msg, "role", None) == "tool":  # type: ignore[attr-defined]
                continue

            history.append(msg)

        logger.debug("Agent %s run completed", rpc.power)
