"""Unit tests for diplomacy engine wrapper functions."""

import tempfile
from pathlib import Path

import pytest

from diplomacy_agents.engine import (
    Game,
    all_possible_orders,
    broadcast_board_state,
    centers,
    export_datc,
    legal_orders,
    press_history,
    send_press,
    snapshot_board,
    submit_orders,
    to_power,
    units,
)
from diplomacy_agents.literals import Power
from diplomacy_agents.models import BoardState, PressMessage


@pytest.fixture()
def fresh_game() -> Game:
    """Return a brand-new standard Diplomacy game instance."""
    return Game()  # uses default classic ruleset


# ---------------------------------------------------------------------------
# Basic state helpers -------------------------------------------------------
# ---------------------------------------------------------------------------


def test_powers_list(fresh_game: Game) -> None:
    """Test that powers list contains exactly the seven great powers."""
    powers = fresh_game.powers
    # Exactly the seven great powers
    assert set(powers) == {
        "AUSTRIA",
        "ENGLAND",
        "FRANCE",
        "GERMANY",
        "ITALY",
        "RUSSIA",
        "TURKEY",
    }


def test_centers_and_units(fresh_game: Game) -> None:
    """Test centers and units helpers return consistent data."""
    for p in fresh_game.powers:
        c = centers(fresh_game, p)
        u = units(fresh_game, p)
        # Each starting unit occupies a supply centre belonging to the power
        assert len(c) == len(u)
        if p == "RUSSIA":
            assert len(c) == 4
        else:
            assert len(c) == 3
        # Every unit location (ignoring coast suffix) should be one of the power's centres
        unit_base_provs = {loc.split("/")[0] for loc in u}
        assert unit_base_provs.issubset(set(c))


def test_snapshot_board(fresh_game: Game) -> None:
    """Test snapshot_board creates complete board state."""
    board: BoardState = snapshot_board(fresh_game)
    # Snapshot should have an entry for each power
    assert set(board.powers.keys()) == set(fresh_game.powers)
    # Russia should have four units recorded
    assert len(board.powers["RUSSIA"].units) == 4


def test_game_properties(fresh_game: Game) -> None:
    """Test Game class properties and methods."""
    # Test phase info
    phase = fresh_game.get_current_phase()
    assert phase == "S1901M"  # Spring 1901 Movement phase

    # Test game not done initially
    assert fresh_game.is_game_done is False

    # Test time property (should return an integer timestamp)
    time_val = fresh_game.time
    assert isinstance(time_val, int)
    assert time_val > 0

    # Test all_locations returns expected locations
    locations = fresh_game.all_locations
    assert "PAR" in locations
    assert "LON" in locations
    assert "BER" in locations
    assert len(locations) > 50  # Should have many locations


# ---------------------------------------------------------------------------
# Orders helpers ------------------------------------------------------------
# ---------------------------------------------------------------------------


def test_legal_orders_subset_all(fresh_game: Game) -> None:
    """Test legal_orders returns subset of all_possible_orders."""
    all_orders = all_possible_orders(fresh_game)
    for p in fresh_game.powers:
        legal = legal_orders(fresh_game, p)
        # Legal orders keys should be subset of all_possible_orders
        assert set(legal.keys()).issubset(all_orders.keys())
        # Every candidate order for the power also exists in the global map
        for orders in legal.values():
            for o in orders:
                assert any(o in v for v in all_orders.values())


def test_submit_orders_accept_and_reject(fresh_game: Game) -> None:
    """Test submit_orders accepts valid orders and rejects invalid ones."""
    power: Power = "GERMANY"  # arbitrary choice
    legal = legal_orders(fresh_game, power)
    # Build a simple order list: first option for every orderable unit
    good_orders = [orders[0] for orders in legal.values()]
    assert submit_orders(fresh_game, power, good_orders) is True
    # An obviously invalid order should be rejected
    bad_orders = ["BOGUS ORDER"]
    assert submit_orders(fresh_game, power, bad_orders) is False


# ---------------------------------------------------------------------------
# Press helpers --------------------------------------------------------------
# ---------------------------------------------------------------------------


def test_press_history_and_broadcast(fresh_game: Game) -> None:
    """Test press message sending and history retrieval."""
    # Send a press message and verify it appears in history
    msg_text = "Hello world"
    press = PressMessage(to="ALL", text=msg_text)  # type: ignore[arg-type]
    send_press(fresh_game, "ENGLAND", press)
    hist = press_history(fresh_game, "ENGLAND")
    assert any(m["message"] == msg_text for m in hist)

    # Broadcast board state and ensure SYSTEM message appended
    state = snapshot_board(fresh_game)
    broadcast_board_state(fresh_game, state)
    last_msg = list(fresh_game.messages.values())[-1]
    assert last_msg.sender == "SYSTEM"
    assert last_msg.recipient == "ALL"


def test_press_private_messages(fresh_game: Game) -> None:
    """Test private press messages between specific powers."""
    # Send private message from France to Germany
    private_text = "Secret alliance proposal"
    private_press = PressMessage(to="GERMANY", text=private_text)  # type: ignore[arg-type]
    send_press(fresh_game, "FRANCE", private_press)

    # France should see the message in their history (as sender)
    france_hist = press_history(fresh_game, "FRANCE")
    assert any(m["message"] == private_text and m["recipient"] == "GERMANY" for m in france_hist)

    # Germany should see the message in their history (as recipient)
    germany_hist = press_history(fresh_game, "GERMANY")
    assert any(m["message"] == private_text and m["sender"] == "FRANCE" for m in germany_hist)

    # Austria should NOT see the private message
    austria_hist = press_history(fresh_game, "AUSTRIA")
    assert not any(m["message"] == private_text for m in austria_hist)


def test_press_self_messages(fresh_game: Game) -> None:
    """Test messages sent from a power to themselves."""
    # Send message from Russia to Russia (notes to self)
    self_text = "Remember to defend Sevastopol"
    self_press = PressMessage(to="RUSSIA", text=self_text)  # type: ignore[arg-type]
    send_press(fresh_game, "RUSSIA", self_press)

    # Russia should see their own message
    russia_hist = press_history(fresh_game, "RUSSIA")
    assert any(
        m["message"] == self_text and m["sender"] == "RUSSIA" and m["recipient"] == "RUSSIA" for m in russia_hist
    )

    # Other powers should not see Russia's self-message
    england_hist = press_history(fresh_game, "ENGLAND")
    assert not any(m["message"] == self_text for m in england_hist)


# ---------------------------------------------------------------------------
# Utility helpers -----------------------------------------------------------
# ---------------------------------------------------------------------------


def test_to_power_valid_and_invalid() -> None:
    """Test to_power validates power tokens correctly."""
    # Valid power tokens should work
    assert to_power("FRANCE") == "FRANCE"
    assert to_power("RUSSIA") == "RUSSIA"

    # Invalid tokens should raise ValueError
    with pytest.raises(ValueError, match="Unknown power"):
        to_power("INVALID")
    with pytest.raises(ValueError, match="Unknown power"):
        to_power("france")  # case sensitive


def test_export_datc(fresh_game: Game) -> None:
    """Test export_datc creates a save file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "test_game.datc"
        export_datc(fresh_game, save_path)
        # File should exist and have some content
        assert save_path.exists()
        assert save_path.stat().st_size > 0
