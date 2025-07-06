"""Unit tests for year-based message filtering helper."""

import pytest

from diplomacy_agents.engine import DiplomacyEngine, Power


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


def _send_msg(eng: DiplomacyEngine, sender: Power, text: str, recipient: Power | None = None) -> None:
    """Record a test message via the engine façade."""
    eng.add_message(sender, text, recipient)


def test_visible_year_history_privacy() -> None:  # noqa: D401
    """Ensure each power only sees public messages and its own private traffic."""
    eng = DiplomacyEngine()

    # Send messages.
    _send_msg(eng, "ENGLAND", "Hello all")  # public
    _send_msg(eng, "ENGLAND", "Bonjour", "FRANCE")  # pm to France
    _send_msg(eng, "ENGLAND", "Guten tag", "GERMANY")  # pm to Germany

    # France should see public + its PM.
    history_fr = eng.get_current_phase_messages("FRANCE")
    assert any(msg.endswith("Hello all") for msg in history_fr)
    assert any(msg.endswith("Bonjour") for msg in history_fr)
    assert not any(msg.endswith("Guten tag") for msg in history_fr)

    # Germany should see public + its PM only.
    history_ge = eng.get_current_phase_messages("GERMANY")
    assert any(msg.endswith("Hello all") for msg in history_ge)
    assert any(msg.endswith("Guten tag") for msg in history_ge)
    assert not any(msg.endswith("Bonjour") for msg in history_ge)
