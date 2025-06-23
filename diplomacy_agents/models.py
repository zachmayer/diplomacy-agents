"""Pydantic data models for the Diplomacy Agents project."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from diplomacy_agents.literals import Location, Power, PressRecipient, UnitType
from diplomacy_agents.types import Order, Phase


# Press models
class PressMessage(BaseModel, frozen=True):
    """
    Diplomacy *press* message authored by one power.

    ``to`` may be either the literal string ``'ALL'`` (broadcast) or the name of
    another power (``'FRANCE'``, ``'GERMANY'``, …).

    Write the ``text`` *in-character* as your power's ruler.  Use it to form
    alliances, negotiate supports, bluff, or issue threats.  Do **not** narrate
    system events (“a new event occurred”); every player receives that
    information already.  Stay concise (≤ 2 kB) so the whole history fits into
    the model context.
    """

    to: PressRecipient = Field(
        ...,
        description="Recipient of the press – either 'ALL' for broadcast or a power token like 'FRANCE'.",
    )
    text: str = Field(
        ...,
        max_length=2_000,
        description="Body of the message written from the sender's perspective.",
    )


class PressLog(BaseModel, frozen=True):
    """Container of press messages for a given phase."""

    phase: Phase
    entries: list[PressMessage]


# Power and Board models
class PowerState(BaseModel, frozen=True):
    """Supply centers and units controlled by a power."""

    centers: tuple[Location, ...]
    units: dict[Location, UnitType]


class BoardState(BaseModel, frozen=True):
    """Mapping of each power to its current state on the board."""

    powers: dict[Power, PowerState]


# Order models
class OrderItem(BaseModel, frozen=True):
    """Single DATC order for one unit."""

    loc: Location = Field(..., description="Province token, e.g. 'PAR'.")
    order: Order = Field(..., min_length=1, description="Full DATC order string for the unit.")


class OrdersInput(BaseModel, frozen=True):
    """Container for a list of orders submitted by a power this phase."""

    @staticmethod
    def _empty_items() -> list[OrderItem]:  # noqa: D401
        """Return a new empty OrderItem list (precisely typed)."""
        return []

    items: list[OrderItem] = Field(default_factory=_empty_items)


# Agent tool return models
class PhaseInfo(BaseModel, frozen=True):
    """Current game phase information."""

    phase: Phase = Field(..., description="Phase token, e.g. 'S1903M'.")


class PowerInfo(BaseModel, frozen=True):
    """Identify which power the agent is playing."""

    power: Power = Field(..., description="Power token, e.g. 'FRANCE'.")


class MessageAck(BaseModel, frozen=True):
    """Acknowledgement that a press message was sent."""

    status: Literal["SENT"] = "SENT"


class OrdersResult(BaseModel, frozen=True):
    """Result of submitting orders."""

    status: Literal[
        "ORDERS ACCEPTED",
        "ORDERS REJECTED: RUN `get_my_possible_orders`",
    ]


class BoardPossibleOrders(BaseModel, frozen=True):
    """Legal orders for all units on the board."""

    orders: dict[Location, list[Order]]


class MyPossibleOrders(BaseModel, frozen=True):
    """Legal orders for the current player's units."""

    orders: dict[Location, list[Order]]


class PressHistory(BaseModel, frozen=True):
    """Recent press messages relevant to the player."""

    messages: list[PressMessage]


__all__ = [
    "BoardPossibleOrders",
    "BoardState",
    "MessageAck",
    "MyPossibleOrders",
    "OrderItem",
    "OrdersInput",
    "OrdersResult",
    "PhaseInfo",
    "PowerInfo",
    "PowerState",
    "PressHistory",
    "PressLog",
    "PressMessage",
]
