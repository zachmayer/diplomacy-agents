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

import json
from collections.abc import Callable
from pathlib import Path

from diplomacy_agents.engine import DiplomacyEngine, PowerViewDTO

# type: ignore[reportPrivateUsage]
from tests.test_phase_orders import (  # type: ignore[reportPrivateUsage]
    _setup_build_russia,
    _setup_disband_germany,
    _setup_retreat_s1901,
)

# ---------------------------------------------------------------------------
# Helpers -------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: object) -> None:  # noqa: D401
    """Serialise *data* as indented JSON to *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _orders_prompt_xml(view: PowerViewDTO) -> str:  # noqa: D401
    """
    Return the legacy XML prompt describing all legal orders.

    The format corresponds to the structure used by earlier agents:

    <orders phase="S1901M" power="FRANCE">
      <unit location="PAR">
        <![CDATA[A PAR H]]>
        <![CDATA[A PAR - BUR]]>
        ...
      </unit>
      ...
    </orders>
    """
    lines: list[str] = [f'<orders phase="{view.phase}" power="{view.power}">']
    for loc, options in view.orders_by_location.items():
        lines.append(f'  <unit location="{loc}">')
        for order in options:
            lines.append(f"    <![CDATA[{order}]]>")
        lines.append("  </unit>")
    lines.append("</orders>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parametrised snapshots -----------------------------------------------------
# ---------------------------------------------------------------------------


_SNAP_CASES: list[tuple[str, str, Callable[[], DiplomacyEngine]]] = [
    ("moves", "FRANCE", DiplomacyEngine),
    ("retreats", "GERMANY", _setup_retreat_s1901),
    ("builds", "RUSSIA", _setup_build_russia),
    ("disbands", "GERMANY", _setup_disband_germany),
]


def _generate_snapshot(tag: str, power: str, factory: Callable[[], DiplomacyEngine]) -> None:  # noqa: D401
    """Generate disk snapshot artefacts for one (case, power) tuple."""
    engine = factory()

    game_state = engine.get_game_state()
    pov: PowerViewDTO = engine.get_power_view(power)  # type: ignore[arg-type]

    orders_model = pov.create_order_model()

    base_dir = Path(__file__).parent / "snapshots" / tag / power

    _write_json(base_dir / "game_state.json", game_state.model_dump(mode="json"))
    _write_json(base_dir / "power_view.json", pov.model_dump(mode="json"))
    _write_json(base_dir / "orders_schema.json", orders_model.model_json_schema())

    (base_dir / "prompt.txt").write_text(_orders_prompt_xml(pov))


# Dynamically generate a pytest test for each snapshot case so test names are
# descriptive in the output without relying on pytest.mark.parametrize (keeps
# extra dependencies out of the tree).


def _make_test(case_tag: str, power: str, factory: Callable[[], DiplomacyEngine]) -> Callable[[], None]:  # noqa: D401
    def _test() -> None:  # noqa: D401
        _generate_snapshot(case_tag, power, factory)
        base_path = Path(__file__).parent / "snapshots" / case_tag / power / "orders_schema.json"
        assert base_path.exists()

    _test.__name__ = f"test_snapshot_{case_tag}_{power.lower()}"
    _test.__doc__ = f"Generate snapshot artefacts for {power} during {case_tag}."
    return _test


for _tag, _pow, _factory in _SNAP_CASES:
    globals()[f"test_snapshot_{_tag}_{_pow.lower()}"] = _make_test(_tag, _pow, _factory)
