"""Library fixtures: the rules mini-SDE plus the modules, drones, charges and implants fits mention."""

import pytest

from apps.sde.models import EveCategory, EveGroup, EveMetaGroup, EveType
from tests.rules.conftest import imported_atxxii, mini_doc, tiny_sde  # noqa: F401

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
def library_sde(tiny_sde):  # noqa: F811
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
