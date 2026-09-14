"""Vocabularies fixed by the game (link scripts) or seeded once (archetypes)."""

import re

# Command burst charges by the two-letter code the practice sheet used: code -> (name, family)
LINK_SCRIPTS: dict[str, tuple[str, str]] = {
    "AE": ("Armor Energizing", "armor"),
    "AR": ("Armor Reinforcement", "armor"),
    "RR": ("Rapid Repair", "armor"),
    "SH": ("Shield Harmonizing", "shield"),
    "SE": ("Shield Extension", "shield"),
    "AS": ("Active Shielding", "shield"),
    "EM": ("Evasive Maneuvers", "skirmish"),
    "IM": ("Interdiction Maneuvers", "skirmish"),
    "RD": ("Rapid Deployment", "skirmish"),
    "EH": ("Electronic Hardening", "info"),
    "ES": ("Electronic Superiority", "info"),
    "SO": ("Sensor Optimization", "info"),
}
MAX_LINK_SCRIPTS = 5
LINK_SCRIPT_RE = re.compile(r"^\((\w\w)\)")  # workbook cells look like "(AE) Energizing"

# (name, is_retired) from the sheet's Configurables list; descriptions are edited in the app
ARCHETYPE_SEED: list[tuple[str, bool]] = [
    ("?????", False),
    ("Armor control", False),
    ("B-war", False),
    ("BS ECM", False),
    ("Drones", False),
    ("Enigma", False),
    ("Flykiller", False),
    ("Heavy armor", False),
    ("Kingslayer", False),
    ("Kite", False),
    ("Medium gun spam", False),
    ("Providence", False),
    ("Rush", False),
    ("Octo", False),
    ("Triple BS core", True),
    ("Tinker", True),
]
