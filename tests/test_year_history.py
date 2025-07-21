"""Unit tests for year-based message filtering helper."""

import pytest

from diplomacy_agents.engine import DiplomacyEngine


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("S1901M", 1901),
        ("F1902B", 1902),
        ("W1910R", 1910),
        ("X", None),
        ("COMPLETED", None),
    ],
)
def test_extract_year(token: str, expected: int | None) -> None:
    """Verify `_extract_year_from_phase` parses year tokens as expected."""
    eng = DiplomacyEngine()
    assert eng._extract_year_from_phase(token) == expected  # type: ignore[protected-access]
