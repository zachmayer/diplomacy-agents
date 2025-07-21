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
from diplomacy_agents.prompts import build_orders_prompt

# type: ignore[reportPrivateUsage]
from tests.test_phase_orders import (  # type: ignore[reportPrivateUsage]
    _setup_build_russia,
    _setup_disband_germany,
    _setup_retreat_germany,
)


# Power is a plain ``str`` value at runtime – annotate as ``str`` to keep Pyright happy.
def _generate_snapshot(tag: str, power: str, factory: Callable[[], DiplomacyEngine]) -> Path:
    """
    Generate and write the *orders* and *press* prompts.

    Returns
    -------
    (orders_path, press_path)
        Filesystem paths of the written prompt XML files so callers can assert
        on their existence (or open them for inspection).

    """
    engine = factory()

    game_state = engine.get_game_state()
    pov: PowerViewDTO = engine.get_power_view(power)  # type: ignore[arg-type]

    base_dir = Path(__file__).parent / "snapshots" / tag
    base_dir.mkdir(parents=True, exist_ok=True)

    # Helper to avoid repetition when writing files.
    def _write(filename: str, content: str) -> Path:
        path = base_dir / filename
        path.write_text(content)
        return path

    file_prefix = f"{tag}_{power.lower()}"

    orders_path = _write(
        f"prompt_{file_prefix}.xml",
        build_orders_prompt(game_state, pov),
    )

    return orders_path


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
    """Generate snapshot files for *(case, power)* and assert they exist."""
    orders_path = _generate_snapshot(case_tag, power, factory)
    assert orders_path.exists()
