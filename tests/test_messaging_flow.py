"""Integration tests for new multi-round messaging flow."""

from __future__ import annotations

import asyncio

from diplomacy_agents.agents import BaseAgent, OutboundPress
from diplomacy_agents.orchestrator import GameOrchestrator, PowerModelMap


class EchoAgent(BaseAgent):
    """Baseline test agent that emits deterministic messages."""

    async def get_orders(self, _game_state: object, _view: object) -> list[str]:  # noqa: D401
        """Return no orders (all units hold)."""
        return []

    async def get_messages(
        self,
        _game_state: object,
        _view: object,
        *,
        rounds_left: int,
    ) -> OutboundPress:
        """Emit deterministic messages for testing the orchestrator flow."""
        # Simulate two-round conversation: first public, then private.
        if not hasattr(self, "_msg_round"):
            self._msg_round = 0  # type: ignore[attr-defined]

        _ = rounds_left  # intentionally unused

        if self._msg_round == 0:
            result = OutboundPress(ALL="Hello all")
        elif self._msg_round == 1:
            result = OutboundPress(FRANCE="Hi France")
        else:
            result = OutboundPress()

        self._msg_round += 1  # type: ignore[attr-defined]
        return result


def _orchestrator_with_custom_agents() -> GameOrchestrator:
    """Return an orchestrator where England is replaced by EchoAgent."""
    orch = GameOrchestrator(
        model_map=PowerModelMap(
            dict.fromkeys(
                [
                    "AUSTRIA",
                    "ENGLAND",
                    "FRANCE",
                    "GERMANY",
                    "ITALY",
                    "RUSSIA",
                    "TURKEY",
                ],
                "hold",
            )
        )
    )
    orch.agents["ENGLAND"] = EchoAgent("ENGLAND")
    return orch


# ---------------------------------------------------------------------------


def test_messaging_rounds_collect_messages() -> None:
    """Ensure orchestrator stores public and private messages correctly."""
    orch = _orchestrator_with_custom_agents()

    asyncio.run(orch.play_turn())

    # Verify that the orchestrator logged the messages and that each power
    # would observe only those addressed to it or broadcast to everyone.

    entries = orch.press_entries

    hist_fr = [text for _phase, _round, _sender, recipient, text in entries if recipient in ("ALL", "FRANCE")]
    assert any("Hello all" in msg for msg in hist_fr)
    assert any("Hi France" in msg for msg in hist_fr)

    hist_ger = [text for _phase, _round, _sender, recipient, text in entries if recipient in ("ALL", "GERMANY")]
    assert any("Hello all" in msg for msg in hist_ger)
    assert not any("Hi France" in msg for msg in hist_ger)
