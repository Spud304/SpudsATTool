"""Hull-size codes and SDE-derived facts the rules layer relies on."""

from apps.sde import constants as sde

SCHEMA_VERSION = 1
RULES_IMPORT_LOCK_KEY = 0x52554C31  # "RUL1"; pg advisory lock shared by CLI and admin imports

# Hull-size codes, canonical order (also the export order of hull_sizes).
HULL_SIZE_FLAG = "FLAG"  # pseudo-size a flagship is promoted to when exempt from its size cap
HULL_SIZE_BS = "BS"
HULL_SIZE_BC = "BC"
HULL_SIZE_CR = "CR"
HULL_SIZE_LC = "LC"
HULL_SIZE_DE = "DE"
HULL_SIZE_FR = "FR"
HULL_SIZE_LF = "LF"
HULL_SIZE_IN = "IN"
HULL_SIZE_CV = "CV"
HULL_SIZES = (
    HULL_SIZE_FLAG,
    HULL_SIZE_BS,
    HULL_SIZE_BC,
    HULL_SIZE_CR,
    HULL_SIZE_LC,
    HULL_SIZE_DE,
    HULL_SIZE_FR,
    HULL_SIZE_LF,
    HULL_SIZE_IN,
    HULL_SIZE_CV,
)
HULL_SIZE_LABELS = {
    HULL_SIZE_FLAG: "Flagship",
    HULL_SIZE_BS: "Battleship",
    HULL_SIZE_BC: "Battlecruiser",
    HULL_SIZE_CR: "Cruiser",
    HULL_SIZE_LC: "Logistics Cruiser",
    HULL_SIZE_DE: "Destroyer",
    HULL_SIZE_FR: "Frigate",
    HULL_SIZE_LF: "Logistics Frigate",
    HULL_SIZE_IN: "Industrial",
    HULL_SIZE_CV: "Corvette",
}

# Natural hull size by SDE group; the fallback when neither the ship entry nor its class says.
GROUP_HULL_SIZES = {
    sde.GROUP_FRIGATE: HULL_SIZE_FR,
    sde.GROUP_ASSAULT_FRIGATE: HULL_SIZE_FR,
    sde.GROUP_INTERCEPTOR: HULL_SIZE_FR,
    sde.GROUP_COVERT_OPS: HULL_SIZE_FR,
    sde.GROUP_ELECTRONIC_ATTACK_SHIP: HULL_SIZE_FR,
    sde.GROUP_STEALTH_BOMBER: HULL_SIZE_FR,
    sde.GROUP_EXPEDITION_FRIGATE: HULL_SIZE_FR,
    sde.GROUP_LOGISTICS_FRIGATE: HULL_SIZE_LF,
    sde.GROUP_DESTROYER: HULL_SIZE_DE,
    sde.GROUP_INTERDICTOR: HULL_SIZE_DE,
    sde.GROUP_COMMAND_DESTROYER: HULL_SIZE_DE,
    sde.GROUP_TACTICAL_DESTROYER: HULL_SIZE_DE,
    sde.GROUP_CRUISER: HULL_SIZE_CR,
    sde.GROUP_HEAVY_ASSAULT_CRUISER: HULL_SIZE_CR,
    sde.GROUP_FORCE_RECON: HULL_SIZE_CR,
    sde.GROUP_COMBAT_RECON: HULL_SIZE_CR,
    sde.GROUP_HEAVY_INTERDICTION_CRUISER: HULL_SIZE_CR,
    sde.GROUP_STRATEGIC_CRUISER: HULL_SIZE_CR,
    sde.GROUP_FLAG_CRUISER: HULL_SIZE_CR,
    sde.GROUP_LOGISTICS: HULL_SIZE_LC,
    sde.GROUP_COMBAT_BATTLECRUISER: HULL_SIZE_BC,
    sde.GROUP_ATTACK_BATTLECRUISER: HULL_SIZE_BC,
    sde.GROUP_COMMAND_SHIP: HULL_SIZE_BC,
    sde.GROUP_BATTLESHIP: HULL_SIZE_BS,
    sde.GROUP_BLACK_OPS: HULL_SIZE_BS,
    sde.GROUP_MARAUDER: HULL_SIZE_BS,
    sde.GROUP_HAULER: HULL_SIZE_IN,
    sde.GROUP_BLOCKADE_RUNNER: HULL_SIZE_IN,
    sde.GROUP_DEEP_SPACE_TRANSPORT: HULL_SIZE_IN,
    sde.GROUP_MINING_BARGE: HULL_SIZE_IN,
    sde.GROUP_EXHUMER: HULL_SIZE_IN,
    sde.GROUP_INDUSTRIAL_COMMAND_SHIP: HULL_SIZE_IN,
    sde.GROUP_EXPEDITION_COMMAND_SHIP: HULL_SIZE_IN,  # Odysseus; banned in AT XXII
    sde.GROUP_CORVETTE: HULL_SIZE_CV,
    sde.GROUP_SPECIAL_EDITION_YACHTS: HULL_SIZE_CV,
}

# T1 hulls the tournament treats as logistics although their SDE group is plain Frigate/Cruiser.
T1_SUPPORT_HULL_SIZES = {
    "Bantam": HULL_SIZE_LF,
    "Burst": HULL_SIZE_LF,
    "Inquisitor": HULL_SIZE_LF,
    "Navitas": HULL_SIZE_LF,
    "Augoror": HULL_SIZE_LC,
    "Osprey": HULL_SIZE_LC,
    "Exequror": HULL_SIZE_LC,
    "Scythe": HULL_SIZE_LC,
}
