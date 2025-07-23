"""Canonical token literals used throughout the project (PEP 695 type aliases)."""

from enum import StrEnum

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


class Location(StrEnum):
    """The locations in the game."""

    ADR = "ADR"
    AEG = "AEG"
    ALB = "ALB"
    ANK = "ANK"
    APU = "APU"
    ARM = "ARM"
    BAL = "BAL"
    BAR = "BAR"
    BEL = "BEL"
    BER = "BER"
    BLA = "BLA"
    BOH = "BOH"
    BOT = "BOT"
    BRE = "BRE"
    BUD = "BUD"
    BUL = "BUL"
    BUL_EC = "BUL/EC"
    BUL_SC = "BUL/SC"
    BUR = "BUR"
    CLY = "CLY"
    CON = "CON"
    DEN = "DEN"
    EAS = "EAS"
    EDI = "EDI"
    ENG = "ENG"
    FIN = "FIN"
    GAL = "GAL"
    GAS = "GAS"
    GRE = "GRE"
    HEL = "HEL"
    HOL = "HOL"
    ION = "ION"
    IRI = "IRI"
    KIE = "KIE"
    LON = "LON"
    LVN = "LVN"
    LVP = "LVP"
    LYO = "LYO"
    MAO = "MAO"
    MAR = "MAR"
    MOS = "MOS"
    MUN = "MUN"
    NAF = "NAF"
    NAO = "NAO"
    NAP = "NAP"
    NTH = "NTH"
    NWG = "NWG"
    NWY = "NWY"
    PAR = "PAR"
    PIC = "PIC"
    PIE = "PIE"
    POR = "POR"
    PRU = "PRU"
    ROM = "ROM"
    RUH = "RUH"
    RUM = "RUM"
    SER = "SER"
    SEV = "SEV"
    SIL = "SIL"
    SKA = "SKA"
    SMY = "SMY"
    SPA = "SPA"
    SPA_NC = "SPA/NC"
    SPA_SC = "SPA/SC"
    STP = "STP"
    STP_NC = "STP/NC"
    STP_SC = "STP/SC"
    SWE = "SWE"
    SWI = "SWI"
    SYR = "SYR"
    TRI = "TRI"
    TUN = "TUN"
    TUS = "TUS"
    TYR = "TYR"
    TYS = "TYS"
    UKR = "UKR"
    VEN = "VEN"
    VIE = "VIE"
    WAL = "WAL"
    WAR = "WAR"
    WES = "WES"
    YOR = "YOR"
