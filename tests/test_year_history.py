"""Unit tests for year-based message filtering helper."""

import pytest

from diplomacy_agents.engine import DiplomacyEngine


# https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.game.html#diplomacy.engine.game.Game.get_current_phase
@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("S1901M", 1901),
        ("F1902B", 1902),
        ("W1910R", 1910),
        ("FORMING", None),
        ("COMPLETED", None),
    ],
)
def test_extract_year(token: str, expected: int | None) -> None:
    """Verify years parse as expected."""
    eng = DiplomacyEngine()
    assert eng.extract_year_from_phase(token) == expected
