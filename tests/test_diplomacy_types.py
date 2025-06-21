"""Runtime guards that our frozen constants still match the diplomacy package."""

from typing import get_args

from diplomacy_agents.engine import Game, to_power
from diplomacy_agents.literals import Location, Power


def test_power_names_match_engine() -> None:
    """Literal Power set should mirror the engine's power list exactly."""
    engine_names: list[str] = list(Game().powers)

    # Ensure static typing is satisfied for the powers mapping

    # Missing?
    for name in engine_names:
        to_power(name)  # raises if literal is absent

    # Extra?
    assert set(engine_names) == set(get_args(Power)), (
        f"Power literals are out of sync: "
        f"Missing: {set(engine_names) - set(get_args(Power))}; "
        f"Extra: {set(get_args(Power)) - set(engine_names)}"
    )


def test_location_names_match_engine() -> None:
    """Literal Location set should mirror engine location list (incl base coasts)."""
    game = Game()
    locs: set[str] = {loc.upper() for loc in game.all_locations}
    locs.update({loc_str.split("/")[0] for loc_str in locs if "/" in loc_str})
    literal_locs: set[str] = set(get_args(Location))

    # Missing?
    assert locs <= literal_locs, f"Missing Location literals: {locs - literal_locs}"

    # Extra?
    assert literal_locs <= locs, f"Extra Location literals: {literal_locs - locs}"
