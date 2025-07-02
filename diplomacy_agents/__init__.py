"""Diplomacy-Agents public package namespace (minimal version after refactor)."""

from diplomacy_agents.engine import (  # noqa: E402
    DiplomacyEngine,
    GameStateDTO,
    Location,
    OrdersList,
    Power,
    PowerViewDTO,
    UnitType,
    flatten_values,
)

# PhaseType is defined in `diplomacy_agents.literals` and re-exported here for
# convenience alongside the engine façade.
from diplomacy_agents.literals import (
    PhaseType,  # noqa: E402
)

__all__: list[str] = [
    "DiplomacyEngine",
    "GameStateDTO",
    "PowerViewDTO",
    "Power",
    "Location",
    "UnitType",
    "PhaseType",
    "OrdersList",
    "flatten_values",
]
