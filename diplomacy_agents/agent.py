"""Agent construction utilities – builds pydantic-ai LLM agents for each power."""

# Ignore unused-function errors triggered by the @agent.tool decorators in this module.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName

from diplomacy_agents.engine import (
    Game,
    all_possible_orders,
    legal_orders,
    press_history,
    send_press,
    snapshot_board,
    submit_orders as engine_submit_orders,
)
from diplomacy_agents.literals import Power
from diplomacy_agents.models import (
    BoardPossibleOrders,
    BoardState,
    MessageAck,
    MyPossibleOrders,
    OrdersInput,
    OrdersResult,
    PhaseInfo,
    PowerInfo,
    PowerState,
    PressHistory,
    PressMessage,
)

__all__ = [
    "DEFAULT_MODEL",
    "Deps",
    "build_agent",
]

logger = logging.getLogger("agents")

DEFAULT_MODEL: KnownModelName = "openai:gpt-4.1-nano-2025-04-14"


@dataclass(slots=True, frozen=True)
class Deps:
    """Typed context passed to every pydantic-ai tool call."""

    game: Game
    power: Power  # e.g. "FRANCE"


def build_agent(_game: Game, power: Power, /, *, model_name: str | KnownModelName = DEFAULT_MODEL) -> Agent[Deps, str]:
    """Return a fully configured pydantic-ai Agent for *power*."""
    system_prompt = f"""
You are playing the Diplomacy power '{power}'. Your goal is to win the game.
Use the TOOLS to inspect the board, and submit orders. Send and receive messages via tools to negotiate with other powers.
The game enforces ALWAYS_WAIT so *submit_orders* must be called each phase.
After using tools, reply with the exact phrase "DONE"
"""

    agent = Agent(
        model=model_name,
        deps_type=Deps,
        system_prompt=system_prompt,
        retries=3,
    )

    # ------------------------------------------------------------------
    # Basic info --------------------------------------------------------
    # ------------------------------------------------------------------

    @agent.tool(name="power_info")
    def power_info_tool(ctx: RunContext[Deps]) -> PowerInfo:  # noqa: D401
        """Return the power you are playing as."""
        logger.info("[%s] TOOLS power_info -> %s", power, ctx.deps.power)
        return PowerInfo(power=ctx.deps.power)

    @agent.tool(name="phase_info")
    def phase_info_tool(ctx: RunContext[Deps]) -> PhaseInfo:
        """Return the current phase of the game, e.g. 'S1903M'."""
        phase = ctx.deps.game.get_current_phase()
        logger.info("[%s] TOOLS phase_info -> %s", power, phase)
        return PhaseInfo(phase=phase)

    # ------------------------------------------------------------------
    # Board state -------------------------------------------------------
    # ------------------------------------------------------------------

    @agent.tool
    def get_board_state(ctx: RunContext[Deps]) -> BoardState:
        """Return full board snapshot."""
        logger.info("[%s] TOOLS get_board_state", power)
        return snapshot_board(ctx.deps.game)

    @agent.tool
    def get_power_state(ctx: RunContext[Deps], target_power: Power) -> PowerState:
        """Return state for *target_power*."""
        if target_power not in ctx.deps.game.powers:
            raise ValueError(f"Unknown power '{target_power}'.")

        board_state = snapshot_board(ctx.deps.game)
        return board_state.powers[target_power]

    @agent.tool
    def get_my_state(ctx: RunContext[Deps]) -> PowerState:
        """Return state for your own power."""
        logger.info("[%s] TOOLS get_my_state", ctx.deps.power)
        return get_power_state(ctx, ctx.deps.power)

    # ------------------------------------------------------------------
    # Orders ------------------------------------------------------------
    # ------------------------------------------------------------------

    @agent.tool
    def get_board_possible_orders(ctx: RunContext[Deps]) -> BoardPossibleOrders:  # noqa: D401
        """Return map of legal orders for all units on board."""
        logger.info("[%s] TOOLS get_board_possible_orders", power)
        orders_map = all_possible_orders(ctx.deps.game)
        return BoardPossibleOrders(orders=orders_map)

    @agent.tool
    def get_my_possible_orders(ctx: RunContext[Deps]) -> MyPossibleOrders:
        """Return all legal orders for your units."""
        logger.info("[%s] TOOLS get_my_orders", power)
        orders_map = legal_orders(ctx.deps.game, ctx.deps.power)
        return MyPossibleOrders(orders=orders_map)

    @agent.tool
    def send_message(ctx: RunContext[Deps], data: PressMessage) -> MessageAck:
        """Send press message."""
        logger.info("[%s] TOOLS send_message %s -> '%s'", ctx.deps.power, data.to, data.text)
        send_press(ctx.deps.game, sender=ctx.deps.power, press=data)
        return MessageAck()

    @agent.tool
    def view_messages(ctx: RunContext[Deps], limit: int = 200) -> PressHistory:
        """Return last *limit* messages involving me."""
        payload = press_history(ctx.deps.game, power, limit=limit)
        messages = [PressMessage(**m) for m in payload]
        logger.info("[%s] TOOLS view_messages(%d) -> %d msgs", power, limit, len(messages))
        return PressHistory(messages=messages)

    @agent.tool
    def submit_orders(ctx: RunContext[Deps], data: OrdersInput) -> OrdersResult:
        """Submit orders for your power."""
        orders = [o.order.strip() for o in data.items if o.order.strip()]
        ok = engine_submit_orders(ctx.deps.game, ctx.deps.power, orders)
        logger.info("[%s] TOOLS submit_orders %s", power, "ACCEPTED" if ok else "REJECTED")
        status = "ORDERS ACCEPTED" if ok else "ORDERS REJECTED: RUN `get_my_orders`"
        return OrdersResult(status=status)

    return agent
