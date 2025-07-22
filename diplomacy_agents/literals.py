"""Canonical token literals used throughout the project (PEP 695 type aliases)."""

from enum import StrEnum
from typing import Literal

__all__ = [
    "PhaseType",
    "UnitType",
    "Power",
    "Location",
]

# https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.game.html
# phase_type: indicates the current phase type. e.g. ‘M’ for Movement, ‘R’ for Retreats, ‘A’ for Adjustment, ‘-‘ for non-playing phase


class PhaseType(StrEnum):
    """The types of phases in the game."""

    MOVEMENT = "M"
    RETREAT = "R"
    ADJUSTMENT = "A"
    NON_PLAYING = "-"


class UnitType(StrEnum):
    """The types of units in the game."""

    ARMY = "A"
    FLEET = "F"
    DISLODGED_ARMY = "*A"
    DISLODGED_FLEET = "*F"


class Power(StrEnum):
    """The powers in the game."""

    ENGLAND = "ENGLAND"
    FRANCE = "FRANCE"
    GERMANY = "GERMANY"
    ITALY = "ITALY"
    RUSSIA = "RUSSIA"
    TURKEY = "TURKEY"
    AUSTRIA = "AUSTRIA"


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
