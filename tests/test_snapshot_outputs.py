# pyright: reportPrivateUsage=false
"""

Generate snapshot JSON artifacts for inspection & regression checks.

This test isn't about behavioural assertions; it serialises the first-turn
state of the `DiplomacyEngine` so humans (and future tests) can eyeball or
compare the structures we expose via our typed façade.

It writes files into tests/snapshots/<phase>/<power>/ … so they can be easily
committed and diffed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from diplomacy_agents.engine import DiplomacyEngine, PowerViewDTO
from diplomacy_agents.prompts import build_orders_prompt, build_press_message_prompt

# type: ignore[reportPrivateUsage]
from tests.test_phase_orders import (  # type: ignore[reportPrivateUsage]
    _setup_build_russia,
    _setup_disband_germany,
    _setup_retreat_germany,
)


def _generate_snapshot(tag: str, power: str, factory: Callable[[], DiplomacyEngine]) -> Path:  # noqa: D401
    """Generate disk snapshot artefacts and return written path."""
    engine = factory()

    # Inject a couple of fake public‐press messages for snapshot context.
    engine.add_public_message("FRANCE", "Greetings all – may we share the spoils?")
    engine.add_public_message("GERMANY", "We shall see, Frankreich.")

    game_state = engine.get_game_state()
    pov: PowerViewDTO = engine.get_power_view(power)  # type: ignore[arg-type]

    base_dir = Path(__file__).parent / "snapshots" / tag
    base_dir.mkdir(parents=True, exist_ok=True)

    prompt_filename = f"prompt_{tag}_{power.lower()}.xml"
    prompt_path = base_dir / prompt_filename
    prompt_path.write_text(build_orders_prompt(game_state, pov))

    # Also generate the public-press prompt (initially with empty history).
    press_prompt_filename = f"prompt_press_{tag}_{power.lower()}.xml"
    press_prompt_path = base_dir / press_prompt_filename
    press_prompt_path.write_text(build_press_message_prompt(game_state, pov))

    return prompt_path


@pytest.mark.parametrize(
    ("case_tag", "power", "factory"),
    [
        ("moves", "FRANCE", DiplomacyEngine),
        ("retreats", "GERMANY", _setup_retreat_germany),
        ("builds", "RUSSIA", _setup_build_russia),
        ("disbands", "GERMANY", _setup_disband_germany),
    ],
)
def test_snapshot_prompt(case_tag: str, power: str, factory: Callable[[], DiplomacyEngine]) -> None:
    """Generate the prompt snapshot for *(case, power)* and assert it exists."""
    path = _generate_snapshot(case_tag, power, factory)
    assert path.exists()
    # Ensure press prompt also exists.
    press_path = path.parent / f"prompt_press_{case_tag}_{power.lower()}.xml"
    assert press_path.exists()
