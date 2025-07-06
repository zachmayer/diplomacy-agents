"""Public‐press semantics: visibility and per‐turn history trimming."""

from __future__ import annotations

from diplomacy_agents.engine import DiplomacyEngine

# ---------------------------------------------------------------------------
# Test 1 – global visibility -------------------------------------------------
# ---------------------------------------------------------------------------


def test_public_press_visible_to_everyone() -> None:  # noqa: D401
    """Every power should see the same global messages via helper."""
    eng = DiplomacyEngine()

    # Two sample public messages.
    eng.add_message("FRANCE", "Bonjour à tous")
    eng.add_message("GERMANY", "Guten Tag")

    expected = {"FRANCE → ALL: Bonjour à tous", "GERMANY → ALL: Guten Tag"}
    history = set(eng.get_current_phase_messages("FRANCE"))
    assert expected.issubset(history)


# ---------------------------------------------------------------------------
# Test 2 – history scoped to current phase ----------------------------------
# ---------------------------------------------------------------------------


def test_press_history_scoped_to_current_phase() -> None:  # noqa: D401
    """After advancing the phase, previous messages must disappear from history."""
    eng = DiplomacyEngine()

    # Phase 1 – add a public message.
    eng.add_message("FRANCE", "Phase1")
    assert any("Phase1" in msg for msg in eng.get_current_phase_messages("ENGLAND"))

    # Advance to next phase (engine tolerates empty orders).
    eng.process_turn()

    # No new messages yet – history should now be empty.
    assert all("Phase1" not in msg for msg in eng.get_current_phase_messages("ENGLAND"))

    # Add a new message in the new phase; only this one should appear.
    eng.add_message("FRANCE", "Phase2")
    history = eng.get_current_phase_messages("ENGLAND")
    assert any("Phase2" in msg for msg in history) and all("Phase1" not in msg for msg in history)  # noqa: PT013
