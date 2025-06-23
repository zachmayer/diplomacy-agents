"""Tests for conversation history pruning helper."""

from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

from diplomacy_agents.agent import DEFAULT_MODEL, build_agent
from diplomacy_agents.conductor import GameRPC
from diplomacy_agents.engine import Game


class DummyGM:
    """Minimal stub exposing ``game`` attribute for ``GameRPC``."""

    def __init__(self) -> None:  # noqa: D401
        """Create fresh inner ``Game`` instance."""
        self.game = Game()


def test_history_pruning_keeps_order() -> None:
    """_prune_history should keep all system messages and last 150 others in order."""
    gm = DummyGM()
    rpc = GameRPC(power="FRANCE", gm=gm)  # type: ignore[arg-type]
    agent = build_agent(rpc, model_name=DEFAULT_MODEL)

    # Build synthetic history: 3 system + 200 user messages.
    messages = [
        ModelRequest(parts=[SystemPromptPart(content="SYS1")]),
        ModelRequest(parts=[SystemPromptPart(content="SYS2")]),
        ModelRequest(parts=[SystemPromptPart(content="SYS3")]),
    ]
    messages.extend(ModelRequest(parts=[UserPromptPart(content=f"U{i}")]) for i in range(200))

    # Retrieve the prune function added during build_agent.
    proc_list = getattr(agent, "history_processors", getattr(agent, "_history_processors", []))
    assert proc_list, "Agent should expose history_processors"
    prune = proc_list[0]

    pruned = prune(None, messages)  # type: ignore[arg-type]

    # Expect 3 system + last 150 user = 153 total
    assert len(pruned) == 153
    # The first three should be the original system messages.
    assert pruned[0] == messages[0]
    assert pruned[1] == messages[1]
    assert pruned[2] == messages[2]
    # The last message should be the original last user message.
    assert pruned[-1] == messages[-1]
