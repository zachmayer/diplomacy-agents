"""Unit tests for year-extraction helper on phase tokens."""

from __future__ import annotations

import pytest

from diplomacy_agents.engine import year_from_short_phase


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
    """Verify that phase tokens map to the correct year (or None)."""
    assert year_from_short_phase(token) == expected
