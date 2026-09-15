"""Shared fixtures: tiny SDE with real ids, the mini ATXXII ruleset, sample fits, dev-login.

App-specific fixtures stay in the per-app conftests; accounts overrides `login_as` with its own defaults.
"""

import pytest

from apps.sde.models import EveCategory, EveFaction, EveGroup, EveMetaGroup, EveRace, EveType

SHIPS = 6
MODULES = 7
GROUPS = {
    25: ("Frigate", SHIPS),
    26: ("Cruiser", SHIPS),
    27: ("Battleship", SHIPS),
    358: ("Heavy Assault Cruiser", SHIPS),
    540: ("Command Ship", SHIPS),
    832: ("Logistics", SHIPS),
    893: ("Electronic Attack Ship", SHIPS),
    1527: ("Logistics Frigate", SHIPS),
    208: ("Sensor Dampener", MODULES),
    303: ("Booster", 20),
    291: ("Weapon Disruptor", MODULES),
}
META = {1: "Tech I", 2: "Tech II", 3: "Storyline", 4: "Faction", 5: "Officer", 6: "Deadspace"}
FACTIONS = {
    500002: "Minmatar Republic",
    500003: "Amarr Empire",
    500004: "Gallente Federation",
    500010: "Guristas Pirates",
    500012: "Blood Raider Covenant",
}
# type_id: (name, group, meta group, faction)
TYPES = {
    22466: ("Astarte", 540, 2, 500004),
    22448: ("Absolution", 540, 2, 500003),
    12003: ("Zealot", 358, 2, 500003),
    17922: ("Ashimmu", 26, 4, 500012),
    29337: ("Augoror Navy Issue", 26, 4, 500003),
    11174: ("Keres", 893, 2, 500004),
    37457: ("Deacon", 1527, 2, 500003),
    609: ("Maulus", 25, 1, 500004),
    11987: ("Guardian", 832, 2, 500003),
    625: ("Augoror", 26, 1, 500003),
    17920: ("Bhaalgorn", 27, 4, 500012),
    17918: ("Rattlesnake", 27, 4, 500010),
    587: ("Rifter", 25, 1, 500002),
}

MINI_ATXXII = """
schema_version: 1
tournament: { code: ATXXII, name: Alliance Tournament XXII, organiser: ccp, year: 2026 }
ruleset:
  fielded_pilots: 10
  point_cap: 200
  max_same_hull: 3
  duplicate_inflation: { enabled: true, mode: per_copy_all }
  flagship: { enabled: true }
  unique_ship_extra_bans: 2
  match: { tiebreak: potential_dps_t0 }
  roster: { max: 40, merc_max: 10 }
  ships_inference: prefix
hull_sizes:
  - { size: FLAG, label: Flagship, max_per_comp: 1 }
  - { size: BS, label: Battleship, max_per_comp: 2, duplicate_surcharge: 4 }
  - { size: BC, label: Battlecruiser, max_per_comp: 3, duplicate_surcharge: 3 }
  - { size: CR, label: Cruiser, max_per_comp: 3, duplicate_surcharge: 2 }
  - { size: LC, label: Logistics Cruiser, max_per_comp: 1, duplicate_surcharge: 1 }
  - { size: FR, label: Frigate, max_per_comp: 3 }
  - { size: LF, label: Logistics Frigate, max_per_comp: 2, duplicate_surcharge: 1 }
group_limits:
  - code: logistics
    label: Logistics
    max: 2
    members: [{ hull_size: LC, weight: 2 }, { hull_size: LF, weight: 1 }]
stages:
  - { code: prelim, best_of: 1, bans_per_side: 3, ban_order: ABBAAB }
  - { code: bracket, best_of: 3, bans_per_side: 4, ban_order: ABBAABAB, avalanche: { loser: 2, winner: 1 }, flagship_uses: 1 }
ship_classes:
  - { name: "Battleship, Pirate Faction", size: BS, points: 53 }
  - { name: Command Ship, size: BC, points: 33 }
  - { name: Logistics Cruiser, size: LC, points: 25 }
  - { name: "Zealot (Heavy Assault Cruiser)", size: CR, points: 21 }
  - { name: Tech 1 Support Cruiser, size: LC, points: 19 }
  - { name: "Cruiser, Pirate Faction", size: CR, points: 18 }
  - { name: "Augoror Navy Issue (Cruiser, Navy Faction)", size: CR, points: 15 }
  - { name: "Keres (Electronic Attack Frigate)", size: FR, points: 12 }
  - { name: Logistics Frigate, size: LF, points: 10 }
  - { name: Tech 1 Disruption Frigate, size: FR, points: 7 }
  - { name: Frigate, size: FR, points: 3 }
ships:
  - { hull: Astarte, class: Command Ship }
  - { hull: Absolution, class: Command Ship }
  - { hull: Ashimmu, class: "Cruiser, Pirate Faction" }
  - { hull: Deacon, class: Logistics Frigate }
  - { hull: Guardian, class: Logistics Cruiser }
  - { hull: Augoror, class: Tech 1 Support Cruiser }
  - { hull: Maulus, class: Tech 1 Disruption Frigate }
  - { hull: Rifter, class: Frigate }
  - { hull: Rattlesnake, class: "Battleship, Pirate Faction" }
  - { hull: Bhaalgorn, class: "Battleship, Pirate Faction", flagship_eligible: false }
point_table:
  label: Test table
  hull_overrides: []
unique_hulls: [Rattlesnake]
module_rules:
  default: { allowed_meta_groups: [Tech I, Tech II] }
  by_group:
    - { groups: [Sensor Dampener, Weapon Disruptor], max_meta_level: 4, hulls: bonused_only }
  banned_groups: [Booster]
  flagship: { allowed_meta_groups: [Tech I, Tech II, Faction, Deadspace, Officer] }
text_sections:
  - { heading: Flagship, body: One pre-declared battleship. }
"""


@pytest.fixture
def tiny_sde(db):
    EveCategory.objects.bulk_create(
        [
            EveCategory(id=SHIPS, name="Ship", published=True),
            EveCategory(id=MODULES, name="Module", published=True),
            EveCategory(id=20, name="Implant", published=True),
        ]
    )
    EveGroup.objects.bulk_create(
        [
            EveGroup(id=gid, category_id=cat, name=name, published=True)
            for gid, (name, cat) in GROUPS.items()
        ]
    )
    EveMetaGroup.objects.bulk_create([EveMetaGroup(id=k, name=v) for k, v in META.items()])
    EveFaction.objects.bulk_create([EveFaction(id=k, name=v) for k, v in FACTIONS.items()])
    EveRace.objects.bulk_create([EveRace(id=1, name="Caldari"), EveRace(id=2, name="Minmatar")])
    EveType.objects.bulk_create(
        [
            EveType(
                id=tid,
                name=name,
                group_id=group,
                meta_group_id=meta,
                faction_id=faction,
                published=True,
                tech_level=2 if meta == 2 else 1,
                meta_level={1: 0, 2: 5, 4: 8}.get(meta),
            )
            for tid, (name, group, meta, faction) in TYPES.items()
        ]
        + [
            EveType(
                id=999001,
                name="Phased Muon Sensor Disruptor I",
                group_id=208,
                meta_group_id=1,
                published=True,
            )
        ]
    )
    return TYPES


@pytest.fixture
def mini_doc(tiny_sde):
    from apps.rules.yaml_io import load_ruleset_document

    return load_ruleset_document(MINI_ATXXII)


@pytest.fixture
def imported_atxxii(mini_doc):
    from apps.core.importing import ImportReport
    from apps.rules.importer import import_ruleset

    report = ImportReport(source="mini")
    ruleset = import_ruleset(mini_doc, report=report)
    return ruleset, report


# library: modules, drones, charges and implants that fits mention

CHARGE, DRONE, IMPLANT, SUBSYSTEM = 8, 18, 20, 32
EXTRA_GROUPS = {
    1770: ("Command Burst", 7),
    65: ("Stasis Web", 7),
    53: ("Energy Weapon", 7),
    100: ("Combat Drone", DRONE),
    83: ("Frequency Crystal", CHARGE),
    1104: ("Nanite Repair Paste", CHARGE),
    954: ("Defensive Systems", SUBSYSTEM),
    749: ("Cyber Shield", IMPLANT),
}
# type_id: (name, group, meta group, meta level)
EXTRA_TYPES = {
    990001: ("Armor Command Burst I", 1770, 1, 0),
    990002: ("Stasis Webifier II", 65, 2, 5),
    990003: ("Federation Navy Stasis Webifier", 65, 4, 8),
    990004: ("Abyssal Stasis Webifier", 65, 15, None),
    990005: ("Remote Sensor Dampener II", 208, 2, 5),
    990006: ("Phased Scoped Remote Sensor Dampener", 208, 1, 4),
    990007: ("Warrior II", 100, 2, 5),
    990008: ("Legion Defensive - Augmented Plating", 954, 14, None),
    990009: ("Zainou 'Gnome' Shield Management SM-705", 749, None, None),
    990010: ("Zainou 'Gypsy' CPU Management EE-603", 749, None, None),
    990011: ("Imperial Navy Multifrequency M", 83, 4, None),
    990012: ("Heavy Beam Laser II", 53, 2, 5),
    990013: ("Nanite Repair Paste", 1104, 1, 0),
    990014: ("Standard Blue Pill Booster", 303, 1, None),
}

ABSO_FIT = """[Absolution, Octo Ewar Abso]

Heavy Beam Laser II, Imperial Navy Multifrequency M
Heavy Beam Laser II, Imperial Navy Multifrequency M
Armor Command Burst I
[Empty High slot]

Stasis Webifier II
Remote Sensor Dampener II


Warrior II x5


Zainou 'Gypsy' CPU Management EE-603
Zainou 'Gnome' Shield Management SM-705


Nanite Repair Paste x500
"""

ABSO_PYFA = """Octo Ewar Abso (Absolution)

DPS: 709 (Weapon: 709, Drone: 0, Volley: 2491)

EHP: 97.6k (Em: 86.5k, Th: 91.7k, Kin: 94.8k, Exp: 156k)
Shield: 7.45k (Em: 12%, Th: 30%, Kin: 74%, Exp: 89%)
Armor: 75.8k (Em: 84%, Th: 85%, Kin: 83%, Exp: 90%)
Hull: 14.3k (Em: 60%, Th: 60%, Kin: 60%, Exp: 60%)

Speed: 1230 m/s
Signature: 1.59k m
Capacitor: 3.16k GJ (Stable at 57%)
Targeting range: 93.8 km
Scan resolution: 315 mm
Sensor strength: 35.4
"""


@pytest.fixture
def library_sde(tiny_sde):
    EveCategory.objects.bulk_create(
        [
            EveCategory(id=CHARGE, name="Charge", published=True),
            EveCategory(id=DRONE, name="Drone", published=True),
            EveCategory(id=SUBSYSTEM, name="Subsystem", published=True),
        ]
    )
    EveGroup.objects.bulk_create(
        [
            EveGroup(id=gid, category_id=cat, name=name, published=True)
            for gid, (name, cat) in EXTRA_GROUPS.items()
        ]
    )
    EveMetaGroup.objects.bulk_create(
        [EveMetaGroup(id=14, name="Tech III"), EveMetaGroup(id=15, name="Abyssal")]
    )
    EveType.objects.bulk_create(
        [
            EveType(
                id=tid,
                name=name,
                group_id=group,
                meta_group_id=meta,
                meta_level=level,
                published=True,
            )
            for tid, (name, group, meta, level) in EXTRA_TYPES.items()
        ]
    )
    return {**tiny_sde, **EXTRA_TYPES}


@pytest.fixture
def login_as(db, client):
    def _login(character_id=1, name="Pilot", role="pilot"):
        resp = client.get(
            "/auth/dev-login", {"character_id": character_id, "name": name, "role": role}
        )
        assert resp.status_code == 302, resp.content[:200]

    return _login
