"""Canonical token literals used throughout the project (PEP 695 type aliases)."""

from typing import Literal

# Import full set of model identifiers recognised by pydantic-ai
from pydantic_ai.models import KnownModelName  # type: ignore[import-not-found]

Power = Literal[
    "AUSTRIA",
    "ENGLAND",
    "FRANCE",
    "GERMANY",
    "ITALY",
    "RUSSIA",
    "TURKEY",
]

PressRecipient = Literal[
    "ALL",
    "AUSTRIA",
    "ENGLAND",
    "FRANCE",
    "GERMANY",
    "ITALY",
    "RUSSIA",
    "TURKEY",
]  # reuse Power tokens plus ALL

UnitType = Literal["A", "F", "*A", "*F"]

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

# ---------------------------------------------------------------------------
# LLM model identifiers ------------------------------------------------------
# ---------------------------------------------------------------------------

# Mapping the **todo list** models to concrete Pydantic-AI identifiers that are
# present in `KnownModelName`.  We purposefully use provider-prefixed names
# where available to avoid ambiguity (e.g. `openai:gpt-4o`).

MODEL_NAMES: tuple[KnownModelName, ...] = (
    # OpenAI family -------------------------------------------------------
    "openai:o3",  # maps original "o3-pro-mode" & "o3" wishlist entries
    "openai:o4-mini",
    "openai:gpt-4.1",
    "openai:gpt-4.1-mini",
    "openai:gpt-4.1-nano",
    "openai:gpt-4o",
    # Anthropic family ----------------------------------------------------
    "anthropic:claude-opus-4-0",  # opus 4
    "anthropic:claude-sonnet-4-0",  # sonnet 4
    # Google Gemini ------------------------------------------------------
    "google-gla:gemini-2.5-pro",  # gemini 2.5 pro
    "google-gla:gemini-2.5-flash",  # gemini 2.5 flash
    # DeepSeek skipped for now (not yet in KnownModelName)
)

# Re-export for convenience --------------------------------------------------
__all__ = [
    "Power",
    "PressRecipient",
    "UnitType",
    "Location",
    "MODEL_NAMES",
]
