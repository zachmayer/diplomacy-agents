"""Diplomacy-Agents public package namespace (minimal version after refactor)."""

# Re-export public API symbols.
from diplomacy_agents.engine import (
    DiplomacyEngine,
    GameStateDTO,
    Location,
    Orders,
    Power,
    PowerViewDTO,
    UnitType,
)

__all__: list[str] = [
    "DiplomacyEngine",
    "GameStateDTO",
    "PowerViewDTO",
    "Power",
    "Location",
    "UnitType",
    "Orders",
]
