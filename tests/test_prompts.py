"""Test the prompts module."""

from __future__ import annotations

import json

from diplomacy_agents.engine import DiplomacyEngine
from diplomacy_agents.enums import Power
from diplomacy_agents.prompts import build_orders_prompt, dump_dict, prune_empty_keys


def test_prune_empty_keys_recursion() -> None:
    """Ensure nested empty containers are removed."""
    data = {
        "keep": 1,
        "drop_empty_list": [],
        "nested": {"drop_empty_dict": {}, "keep_nested": {"x": 2}},
        "list_of_lists": [[1]],
        "none_val": None,
    }

    expected = {"keep": 1, "nested": {"keep_nested": {"x": 2}}, "list_of_lists": [[1]]}
    assert prune_empty_keys(data) == expected


def test_dump_dict_prunes_and_serialises() -> None:
    """``dump_dict`` should prune empties and return valid JSON."""
    src: dict[str, object] = {"a": [], "b": {"x": 1, "y": []}}
    data: dict[str, object] = json.loads(dump_dict(src))
    assert data == {"b": {"x": 1}}


def _first_orders(engine: DiplomacyEngine, power: Power) -> tuple[str, ...]:
    """Return first legal order for each unit."""
    return tuple(opts[0] for opts in engine.possible_orders[power].values() if opts)


def test_build_orders_prompt_basic() -> None:
    """Basic smoke-test of prompt generation."""
    eng = DiplomacyEngine()
    for pwr in eng.powers:
        eng.set_orders(pwr, _first_orders(eng, pwr))
    eng.process_turn()

    prompt = build_orders_prompt(eng, Power.AUSTRIA)
    assert "<main-goal>" in prompt
    # ``all_units`` would be empty at game start, so it should be pruned.
    assert "all_units" in prompt
    assert "AUSTRIA" in prompt
