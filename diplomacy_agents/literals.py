"""Canonical token literals used throughout the project (PEP 695 type aliases)."""

from typing import TYPE_CHECKING, Literal

# Import full set of model identifiers recognised by pydantic-ai with graceful
# fallback when the package is unavailable in the current environment (e.g. during
# static analysis in isolation).

if TYPE_CHECKING:  # pragma: no cover – only for type checkers
    from pydantic_ai.models import KnownModelName as _KnownModelName
else:  # pragma: no cover – runtime fallback
    _KnownModelName = str  # noqa: ANN001 – simple alias for runtime

type KnownModelName = _KnownModelName

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

# Short phase type code used throughout the engine and DTOs -----------------
PhaseType = Literal["M", "R", "A"]  # Movement, Retreats, Adjustments

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

# Re-export for convenience --------------------------------------------------
__all__ = [
    "Power",
    "PressRecipient",
    "UnitType",
    "Location",
    "PhaseType",
]
