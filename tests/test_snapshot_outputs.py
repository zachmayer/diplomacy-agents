# pyright: reportPrivateUsage=false
"""
Generate snapshot JSON / prompt artefacts for manual inspection.

Each parametrised case serialises the board state and the generated orders
prompt for a specific power, writing files under *artifacts/snapshots/*.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from diplomacy_agents.engine import DiplomacyEngine
from diplomacy_agents.enums import Power
from diplomacy_agents.prompts import build_orders_prompt
from tests.test_phase_orders import (
    _setup_build_russia,
    _setup_disband_germany,
    _setup_retreat_germany,
)

# ---------------------------------------------------------------------------#
# Helper                                                                      #
# ---------------------------------------------------------------------------#


def _generate_snapshot(tag: str, power: Power, factory: Callable[[], DiplomacyEngine]) -> Path:
    """Build the orders prompt for *(tag, power)*, write it to disk, and return the path."""
    engine = factory()

    base_dir = Path("artifacts") / "snapshots"
    base_dir.mkdir(parents=True, exist_ok=True)

    file_path = base_dir / f"prompt_{tag}_{power.value.lower()}.xml"
    file_path.write_text(build_orders_prompt(engine, power))

    return file_path


# ---------------------------------------------------------------------------#
# Parametrised snapshot generation                                           #
# ---------------------------------------------------------------------------#


@pytest.mark.parametrize(
    ("case_tag", "power", "factory"),
    [
        ("moves", Power.FRANCE, DiplomacyEngine),
        ("retreats", Power.GERMANY, _setup_retreat_germany),
        ("builds", Power.RUSSIA, _setup_build_russia),
        ("disbands", Power.GERMANY, _setup_disband_germany),
    ],
)
def test_snapshot_prompt(case_tag: str, power: Power, factory: Callable[[], DiplomacyEngine]) -> None:
    """Generate snapshot prompt files and assert they were written."""
    prompt_path = _generate_snapshot(case_tag, power, factory)
    assert prompt_path.exists()
