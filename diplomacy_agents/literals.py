"""Canonical token literals used throughout the project (PEP 695 type aliases)."""

from typing import Literal

Power = Literal[
    "AUSTRIA",
    "ENGLAND",
    "FRANCE",
    "GERMANY",
    "ITALY",
    "RUSSIA",
    "TURKEY",
]
UnitType = Literal["A", "F", "*A", "*F"]

# https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.game.html
# phase_type: indicates the current phase type. e.g. ‘M’ for Movement, ‘R’ for Retreats, ‘A’ for Adjustment, ‘-‘ for non-playing phase
PhaseType = Literal["M", "R", "A", "-"]

Location = Literal[
    "ADR",
    "AEG",
    "ALB",
    "ANK",
    "APU",
    "ARM",
    "BAL",
    "BAR",
    "BEL",
    "BER",
    "BLA",
    "BOH",
    "BOT",
    "BRE",
    "BUD",
    "BUL",
    "BUL/EC",
    "BUL/SC",
    "BUR",
    "CLY",
    "CON",
    "DEN",
    "EAS",
    "EDI",
    "ENG",
    "FIN",
    "GAL",
    "GAS",
    "GRE",
    "HEL",
    "HOL",
    "ION",
    "IRI",
    "KIE",
    "LON",
    "LVN",
    "LVP",
    "LYO",
    "MAO",
    "MAR",
    "MOS",
    "MUN",
    "NAF",
    "NAO",
    "NAP",
    "NTH",
    "NWG",
    "NWY",
    "PAR",
    "PIC",
    "PIE",
    "POR",
    "PRU",
    "ROM",
    "RUH",
    "RUM",
    "SER",
    "SEV",
    "SIL",
    "SKA",
    "SMY",
    "SPA",
    "SPA/NC",
    "SPA/SC",
    "STP",
    "STP/NC",
    "STP/SC",
    "SWE",
    "SWI",
    "SYR",
    "TRI",
    "TUN",
    "TUS",
    "TYR",
    "TYS",
    "UKR",
    "VEN",
    "VIE",
    "WAL",
    "WAR",
    "WES",
    "YOR",
]

# Canonical tuple of the seven powers in deterministic order.
POWERS: tuple[Power, ...] = (
    "ENGLAND",
    "FRANCE",
    "GERMANY",
    "ITALY",
    "RUSSIA",
    "TURKEY",
    "AUSTRIA",
)

# ---------------------------------------------------------------------------
# Model presets
# ---------------------------------------------------------------------------

# Local model specifiers recognised by the project (plus baseline agents).

LOCAL_MODEL_NAMES: tuple[str, ...] = (
    # OpenAI ------------------------------------------------------------
    "openai:gpt-4.1-2025-04-14",
    "openai:gpt-4.1-mini-2025-04-14",
    "openai:gpt-4.1-nano-2025-04-14",
    "openai:gpt-4o-2024-11-20",
    "openai:gpt-4o-mini-2024-07-18",
    "openai:o3-2025-04-16",
    "openai:o3-mini-2025-01-31",
    "openai:o4-mini-2025-04-16",
    # Google Gemini – GLA ---------------------------------------------
    "google-gla:gemini-2.5-flash",
    "google-gla:gemini-2.5-pro",
    # Anthropic Claude -------------------------------------------------
    "anthropic:claude-3-5-haiku-20241022",
    "anthropic:claude-3-5-sonnet-20241022",
    "anthropic:claude-3-7-sonnet-20250219",
    "anthropic:claude-4-opus-20250514",
    "anthropic:claude-4-sonnet-20250514",
    "anthropic:claude-opus-4-20250514",
    "anthropic:claude-sonnet-4-20250514",
    # DeepSeek --------------------------------------------------------
    "deepseek:deepseek-reasoner",
    # Baselines --------------------------------------------------------
    "hold",
    "random",
)

__all__ = [
    "Power",
    "UnitType",
    "Location",
    "PhaseType",
    "POWERS",
    "LOCAL_MODEL_NAMES",
]
