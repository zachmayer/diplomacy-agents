"""
Generate snapshot JSON artifacts for inspection & regression checks.

This test isn't about behavioural assertions; it serialises the first-turn
state of the `DiplomacyEngine` so humans (and future tests) can eyeball or
compare the structures we expose via our typed façade.

It writes files into tests/snapshots/<phase>/<power>/ … so they can be easily
committed and diffed.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from diplomacy_agents.engine import DiplomacyEngine, PowerViewDTO

# ---------------------------------------------------------------------------
# Helpers -------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: object) -> None:  # noqa: D401
    """Serialise *data* as indented JSON to *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _prompt_from_schema(model: type[BaseModel]) -> str:  # noqa: D401
    """Very small-scale imitation of pydantic-ai's output‐object prompt."""
    schema = json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
    doc = (model.__doc__ or "").strip()
    pieces = [doc] if doc else []
    pieces.append("When responding, provide a JSON array adhering to this schema:")
    pieces.append(schema)
    return "\n\n".join(pieces)


# ---------------------------------------------------------------------------
# Test (snapshot generator) --------------------------------------------------
# ---------------------------------------------------------------------------


def test_generate_france_moves_snapshot() -> None:  # noqa: D401
    """Dump snapshots for France during the initial movement phase."""
    engine = DiplomacyEngine()
    game_state = engine.get_game_state()
    france_view: PowerViewDTO = engine.get_power_view("FRANCE")

    orders_model = france_view.create_order_model()

    base_dir = Path(__file__).parent / "snapshots" / "moves" / "FRANCE"

    _write_json(base_dir / "game_state.json", game_state.model_dump(mode="json"))
    _write_json(base_dir / "power_view.json", france_view.model_dump(mode="json"))
    _write_json(base_dir / "orders_schema.json", orders_model.model_json_schema())

    (base_dir / "prompt.txt").write_text(_prompt_from_schema(orders_model))

    # Minimal assertion so pytest marks test as passed.
    assert (base_dir / "orders_schema.json").exists()
