"""
Agent construction utilities – builds pydantic-ai LLM agents for each power.

This *new* version is exclusively designed for the **event-driven conductor**
architecture.  The only dependency passed to the Agent is a
``diplomacy_agents.conductor.GameRPC`` instance which exposes a minimal, typed
RPC surface (board_state, my_possible_orders, send_press, submit_orders).
"""

# Ignore unused-function errors triggered by the @agent.tool decorators in this module.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import logging

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName

from diplomacy_agents.conductor import GameRPC
from diplomacy_agents.engine import all_possible_orders
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
    PressMessage,
)

__all__ = [
    "DEFAULT_MODEL",
    "build_agent",
]

logger = logging.getLogger("agents")

DEFAULT_MODEL: KnownModelName = "openai:gpt-4.1-nano-2025-04-14"


def build_agent(rpc: GameRPC, /, *, model_name: str | KnownModelName = DEFAULT_MODEL) -> Agent[GameRPC, str]:
    """Return a fully configured pydantic-ai Agent bound to *rpc.power*."""
    power: Power = rpc.power

    system_prompt = (
        f"You are playing the Diplomacy power '{power}'. Your goal is to win the game.\n"
        "Use the TOOLS to inspect the board, negotiate, and submit orders.\n"
        "The game enforces ALWAYS_WAIT so *submit_orders* must be called each phase.\n"
        'After using tools, reply with the exact phrase "DONE"'
    )

    agent: Agent[GameRPC, str] = Agent(
        model=model_name,
        deps_type=GameRPC,
        system_prompt=system_prompt,
        retries=3,
    )

    # ------------------------------------------------------------------
    # Basic info --------------------------------------------------------
    # ------------------------------------------------------------------

    @agent.tool(name="power_info")
    def power_info_tool(ctx: RunContext[GameRPC]) -> PowerInfo:  # noqa: D401
        """Return the power you are playing as."""
        logger.info("[%s] TOOLS power_info -> %s", power, ctx.deps.power)
        return PowerInfo(power=ctx.deps.power)

    @agent.tool(name="phase_info")
    def phase_info_tool(ctx: RunContext[GameRPC]) -> PhaseInfo:
        """Return the current phase of the game, e.g. 'S1903M'."""
        phase = ctx.deps.gm.game.get_current_phase()
        logger.info("[%s] TOOLS phase_info -> %s", power, phase)
        return PhaseInfo(phase=phase)

    # ------------------------------------------------------------------
    # Board state -------------------------------------------------------
    # ------------------------------------------------------------------

    @agent.tool
    def get_board_state(ctx: RunContext[GameRPC]) -> BoardState:
        """Return full board snapshot."""
        logger.info("[%s] TOOLS get_board_state", power)
        return ctx.deps.board_state()

    @agent.tool
    def get_power_state(ctx: RunContext[GameRPC], target_power: Power) -> PowerState:
        """Return state for *target_power*."""
        game_state = ctx.deps.board_state()
        if target_power not in game_state.powers:
            raise ValueError(f"Unknown power '{target_power}'.")
        return game_state.powers[target_power]

    @agent.tool
    def get_my_state(ctx: RunContext[GameRPC]) -> PowerState:
        """Return state for your own power."""
        logger.info("[%s] TOOLS get_my_state", power)
        return get_power_state(ctx, power)

    # ------------------------------------------------------------------
    # Orders ------------------------------------------------------------
    # ------------------------------------------------------------------

    @agent.tool
    def get_board_possible_orders(ctx: RunContext[GameRPC]) -> BoardPossibleOrders:  # noqa: D401
        """Return map of legal orders for all units on board."""
        logger.info("[%s] TOOLS get_board_possible_orders", power)
        orders_map = all_possible_orders(ctx.deps.gm.game)
        return BoardPossibleOrders(orders=orders_map)

    @agent.tool
    def get_my_possible_orders(ctx: RunContext[GameRPC]) -> MyPossibleOrders:
        """Return all legal orders for your units."""
        logger.info("[%s] TOOLS get_my_orders", power)
        orders_map = ctx.deps.my_possible_orders()
        return MyPossibleOrders(orders=orders_map)

    @agent.tool
    async def send_message(ctx: RunContext[GameRPC], data: PressMessage) -> MessageAck:
        """Send press message."""
        logger.info("[%s] TOOLS send_message %s -> '%s'", power, data.to, data.text)
        await ctx.deps.send_press(data.to, data.text)
        return MessageAck()

    @agent.tool
    async def submit_orders(ctx: RunContext[GameRPC], data: OrdersInput) -> OrdersResult:
        """Submit orders for your power."""
        orders = [o.order.strip() for o in data.items if o.order.strip()]
        ok = await ctx.deps.submit_orders(orders)
        logger.info("[%s] TOOLS submit_orders %s", power, "ACCEPTED" if ok else "REJECTED")
        status = "ORDERS ACCEPTED" if ok else "ORDERS REJECTED: RUN `get_my_orders`"
        return OrdersResult(status=status)

    return agent
