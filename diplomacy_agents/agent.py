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
from pydantic_ai.messages import ModelMessage, SystemPromptPart
from pydantic_ai.models import KnownModelName

from diplomacy_agents.conductor import GameRPC
from diplomacy_agents.literals import Power
from diplomacy_agents.models import (
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

    system_prompt = f"""
You are a PLAYER in the board game *Diplomacy* controlling the power '{power}'.

A separate *game orchestrator* handles timing, board updates, and result
publication.  You never have to describe those events – everyone already sees
them.

YOUR JOB EACH PHASE
===================
1. Gather intelligence with the inspection TOOLS (optional).
2. Negotiate with other powers using *send_message* (optional).  Only send
   press that advances {power}'s interests.
3. Call *submit_orders* with **one legal order per unit** *before* you finish.
   You may resubmit later to replace earlier orders. Use the *get_my_possible_orders* tool to get the list of legal orders for each unit.

Guidelines for press
+--------------------
• Write *in-character* as the ruler of {power}.
• Do **not** narrate orchestrator or system events (e.g. "A new event has
  occurred").  Focus on alliances, threats, and concrete proposals.

After executing all desired tool calls, reply with the single word **DONE** so
the orchestrator knows you are finished for now.
"""

    # ---------------------------------------------------------------
    # History processor – keep ALL system messages but only the most
    # recent 150 non-system messages to stay within token limits.
    # ---------------------------------------------------------------

    def _prune_history(_ctx: RunContext[GameRPC], messages: list[ModelMessage]) -> list[ModelMessage]:  # noqa: ANN001
        """
        Keep all system messages and the *last 150* non-system messages in order.

        This simple heuristic ensures:
        1. Orchestrator/system context is never lost.
        2. Token usage from free-text press remains bounded.
        """
        # Gather indices of non-system messages.
        non_sys_indices: list[int] = [
            i for i, m in enumerate(messages) if not any(isinstance(p, SystemPromptPart) for p in m.parts)
        ]

        # Drop oldest non-system messages if we exceed the budget.
        drop: set[int] = set()
        if len(non_sys_indices) > 150:
            drop = set(non_sys_indices[: len(non_sys_indices) - 150])

        return [m for idx, m in enumerate(messages) if idx not in drop]

    agent: Agent[GameRPC, str] = Agent(
        model=model_name,
        deps_type=GameRPC,
        system_prompt=system_prompt,
        retries=3,
        history_processors=[_prune_history],
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
        """Return full board snapshot (all powers, centres & units)."""
        logger.info("[%s] TOOLS get_board_state", power)
        return ctx.deps.board_state()

    @agent.tool
    def get_power_state(ctx: RunContext[GameRPC], target_power: Power) -> PowerState:
        """Return centres & units for *target_power* only."""
        game_state = ctx.deps.board_state()
        if target_power not in game_state.powers:
            raise ValueError(f"Unknown power '{target_power}'.")
        return game_state.powers[target_power]

    @agent.tool
    def get_my_state(ctx: RunContext[GameRPC]) -> PowerState:
        """Return *only your* centres & units for quick reference."""
        logger.info("[%s] TOOLS get_my_state", power)
        return get_power_state(ctx, power)

    # ------------------------------------------------------------------
    # Orders ------------------------------------------------------------
    # ------------------------------------------------------------------

    @agent.tool
    def get_my_possible_orders(ctx: RunContext[GameRPC]) -> MyPossibleOrders:
        """Return all legal orders for your units."""
        logger.info("[%s] TOOLS get_my_orders", power)
        orders_map = ctx.deps.my_possible_orders()
        return MyPossibleOrders(orders=orders_map)

    @agent.tool
    async def send_message(ctx: RunContext[GameRPC], data: PressMessage) -> MessageAck:
        """
        Send a press message *from your power's perspective*.

        * ``data.to`` – recipient: ``'ALL'`` for broadcast or a specific power token (e.g. ``'RUSSIA'``).
        * ``data.text`` – write as the leader of your power. Persuade, deceive or threaten as needed. Avoid meta-commentary.

        Use this tool *strategically* – forge alliances, sow discord, or negotiate supports to advance your victory conditions.
        """
        logger.info("[%s] TOOLS send_message %s -> '%s'", power, data.to, data.text)
        await ctx.deps.send_press(data.to, data.text)
        return MessageAck()

    @agent.tool
    async def submit_orders(ctx: RunContext[GameRPC], data: OrdersInput) -> OrdersResult:
        """
        Submit orders for the *current* phase.

        Workflow for every phase:
        1. Invoke ``get_my_possible_orders`` to fetch the authoritative list of
           legal orders for each of your units.
        2. Pick *one* order per unit and build an ``OrdersInput`` object where
           every ``order`` string is copied *verbatim* from that list.
        3. Call this tool.  If an order is illegal the engine rejects the whole
           batch and your previous orders (if any) remain in force.

        You may call this tool multiple times within a phase – later submissions
        *override* earlier ones.  Submit early, update later if diplomacy
        changes the plan, but ensure a valid set is on file before the deadline.
        """
        orders = [o.order.strip() for o in data.items if o.order.strip()]
        ok = await ctx.deps.submit_orders(orders)
        logger.info("[%s] TOOLS submit_orders %s", power, "ACCEPTED" if ok else "REJECTED")
        status = "ORDERS ACCEPTED" if ok else "ORDERS REJECTED: RUN `get_my_possible_orders`"
        return OrdersResult(status=status)

    return agent
