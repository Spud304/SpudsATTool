"""A hand-built ATXXII engine spec with real type ids, for engine tests that need no database."""

from apps.rules.engine import (
    FlagshipRules,
    GroupLimit,
    GroupLimitMember,
    HullSpec,
    PointTable,
    RulesetSpec,
    SizeRule,
    SlotInput,
    StageSpec,
)

ASTARTE, ABSOLUTION, ZEALOT, ASHIMMU, ANI = 22466, 22448, 12003, 17922, 29337
KERES, DEACON, MAULUS, GUARDIAN, AUGOROR = 11174, 37457, 609, 11987, 625
BHAALGORN, RATTLESNAKE, RIFTER = 17920, 17918, 587

HULLS = {
    ASTARTE: HullSpec(ASTARTE, "Astarte", "BC", "Command Ship", "legal", False),
    ABSOLUTION: HullSpec(ABSOLUTION, "Absolution", "BC", "Command Ship", "legal", False),
    ZEALOT: HullSpec(ZEALOT, "Zealot", "CR", "Zealot (Heavy Assault Cruiser)", "legal", False),
    ASHIMMU: HullSpec(ASHIMMU, "Ashimmu", "CR", "Cruiser, Pirate Faction", "legal", False),
    ANI: HullSpec(
        ANI,
        "Augoror Navy Issue",
        "CR",
        "Augoror Navy Issue (Cruiser, Navy Faction)",
        "legal",
        False,
    ),
    KERES: HullSpec(KERES, "Keres", "FR", "Keres (Electronic Attack Frigate)", "legal", False),
    DEACON: HullSpec(DEACON, "Deacon", "LF", "Logistics Frigate", "legal", False),
    MAULUS: HullSpec(MAULUS, "Maulus", "FR", "Tech 1 Disruption Frigate", "legal", False),
    GUARDIAN: HullSpec(GUARDIAN, "Guardian", "LC", "Logistics Cruiser", "legal", False),
    AUGOROR: HullSpec(AUGOROR, "Augoror", "LC", "Tech 1 Support Cruiser", "legal", False),
    BHAALGORN: HullSpec(BHAALGORN, "Bhaalgorn", "BS", "Battleship, Pirate Faction", "legal", False),
    RATTLESNAKE: HullSpec(
        RATTLESNAKE,
        "Rattlesnake",
        "BS",
        "Battleship, Pirate Faction",
        "legal",
        True,
        is_unique=True,
    ),
    RIFTER: HullSpec(RIFTER, "Rifter", "FR", "Frigate", "legal", False),
}

TABLE = PointTable(
    version_id=1,
    class_points={
        "Command Ship": 33,
        "Zealot (Heavy Assault Cruiser)": 21,
        "Cruiser, Pirate Faction": 18,
        "Augoror Navy Issue (Cruiser, Navy Faction)": 15,
        "Keres (Electronic Attack Frigate)": 12,
        "Logistics Frigate": 10,
        "Tech 1 Disruption Frigate": 7,
        "Logistics Cruiser": 25,
        "Tech 1 Support Cruiser": 19,
        "Battleship, Pirate Faction": 53,
        "Frigate": 3,
    },
)

SIZE_RULES = {
    "FLAG": SizeRule(1, 0),
    "BS": SizeRule(2, 4),
    "BC": SizeRule(3, 3),
    "CR": SizeRule(3, 2),
    "LC": SizeRule(1, 1),
    "DE": SizeRule(3, 1),
    "FR": SizeRule(3, 0),
    "LF": SizeRule(2, 1),
    "IN": SizeRule(3, 2),
    "CV": SizeRule(3, 0),
}
LOGISTICS = GroupLimit(
    "logistics",
    "Logistics",
    2,
    (GroupLimitMember(hull_size="LC", weight=2), GroupLimitMember(hull_size="LF", weight=1)),
)

SPEC = RulesetSpec(
    code="ATXXII",
    fielded_pilots=10,
    point_cap=200,
    max_same_hull=3,
    inflation_enabled=True,
    inflation_mode="per_copy_all",
    size_rules=SIZE_RULES,
    group_limits=(LOGISTICS,),
    flagship=FlagshipRules(enabled=True),
    unique_ship_extra_bans=2,
    tiebreak_rule="potential_dps_t0",
)

AG7_SPEC = RulesetSpec(
    code="AG7",
    fielded_pilots=7,
    point_cap=75,
    max_same_hull=1,
    inflation_enabled=False,
    inflation_mode="per_copy_all",
    size_rules={k: SizeRule(None, 0) for k in ("BS", "BC", "CR", "LC", "DE", "FR", "LF")},
    group_limits=(LOGISTICS,),
)

BRACKET = StageSpec(
    "bracket",
    3,
    4,
    "ABBAABAB",
    avalanche_enabled=True,
    avalanche_loser_bans=2,
    avalanche_winner_bans=1,
    flagship_uses=1,
)
PRELIM = StageSpec("prelim", 1, 3, "ABBAAB")
AG_STAGE = StageSpec("single", 1, 2, "ABBA")

OF99_SET1 = (ASTARTE, ASTARTE, ABSOLUTION, ZEALOT, ASHIMMU, ANI, KERES, DEACON, DEACON, MAULUS)


def slots(
    *type_ids: int | None, flagship_at: int | None = None, links_at: tuple[int, ...] = ()
) -> list[SlotInput]:
    return [
        SlotInput(i, t, is_flagship=(i == flagship_at), has_links=(i in links_at))
        for i, t in enumerate(type_ids, start=1)
    ]
