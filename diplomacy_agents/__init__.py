"""Diplomacy-Agents public package namespace (minimal version after refactor)."""

# Re-export public API symbols.
from diplomacy_agents.engine import DiplomacyEngine, Orders, PowerViewDTO

__all__: list[str] = [
    "DiplomacyEngine",
    "PowerViewDTO",
    "Orders",
]
