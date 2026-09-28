from hypothesis import given
from hypothesis import strategies as st

from apps.library.eft import NO_HEADER, parse_eft
from tests.conftest import ABSO_FIT


def test_header_and_items():
    p = parse_eft(ABSO_FIT)
    assert p.ok and p.hull_name == "Absolution" and p.fit_name == "Octo Ewar Abso"
    names = [i.name for i in p.items]
    assert names.count("Heavy Beam Laser II") == 2
    assert "[Empty High slot]" not in names and "" not in names
    lasers = [i for i in p.items if i.name == "Heavy Beam Laser II"]
    assert all(i.charge == "Imperial Navy Multifrequency M" for i in lasers)
    drones = next(i for i in p.items if i.name == "Warrior II")
    assert drones.quantity == 5 and drones.charge is None
    paste = next(i for i in p.items if i.name == "Nanite Repair Paste")
    assert paste.quantity == 500
    assert p.items[0].line_no == 3
    assert "Imperial Navy Multifrequency M" in p.names


def test_header_without_name_uses_hull():
    p = parse_eft("[Rifter]\n200mm AutoCannon II, EMP S")
    assert p.hull_name == "Rifter" and p.fit_name == "Rifter"


def test_offline_and_crlf_and_nbsp():
    p = parse_eft("[Rifter, x]\r\nDamage Control II/OFFLINE\r\n1MN\xa0Afterburner II\r\n")
    assert p.items[0].offline and p.items[0].name == "Damage Control II"
    assert p.items[1].name == "1MN Afterburner II" and not p.items[1].offline
    p = parse_eft("[Rifter, x]\nArmor Command Burst II, Armor Reinforcement Charge /offline\n")
    assert p.items[0].offline and p.items[0].charge == "Armor Reinforcement Charge"


def test_mutation_metadata_skipped_with_warning():
    text = "[Rifter, x]\nAbyssal Stasis Webifier\n  [Stasis Webifier II, Decayed Mutaplasmid]\n  speedFactor 61\n"
    p = parse_eft(text)
    assert [i.name for i in p.items] == ["Abyssal Stasis Webifier"]
    assert len(p.warnings) == 2


def test_no_header():
    p = parse_eft("Damage Control II\n")
    assert not p.ok and p.errors[0].startswith(NO_HEADER)
    assert not parse_eft("   \n\n").ok


def test_blank_banks_do_not_change_items():
    a = parse_eft("[Rifter, x]\nA\n\n\n\nB\n")
    b = parse_eft("[Rifter, x]\nA\nB\n")
    assert [i.name for i in a.items] == [i.name for i in b.items]


name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters=" '-"),
    min_size=1,
).filter(lambda s: s.strip() and not s.startswith("[") and s == s.strip())


@given(name=name_st, charge=name_st, qty=st.integers(min_value=1, max_value=999))
def test_item_line_roundtrip(name, charge, qty):
    p = parse_eft(f"[Rifter, r]\n{name}, {charge} x{qty}\n")
    assert p.ok and len(p.items) == 1
    item = p.items[0]
    assert item.name == name and item.charge == charge and item.quantity == qty


PYFA_MUTATED = """[Skua, 10mn skua]

Mizuro's Modified Ballistic Control System [1]
Caldari Navy Ballistic Control System [2]
Missile Guidance Computer II

Corelum A-Type 10MN Afterburner [3]


Caldari Navy Nova Light Missile x300


[1] Mizuro's Modified Ballistic Control System
  Glorified Unstable Ballistic Control System Mutaplasmid
  cpu 39.8008, missileDamageMultiplierBonus 1.144181, speedMultiplier 0.8708828
[2] Caldari Navy Ballistic Control System
  Unstable Ballistic Control System Mutaplasmid
  cpu 34.6728, missileDamageMultiplierBonus 1.138099, speedMultiplier 0.870865
"""


def test_mutated_modules_are_marked_by_their_reference():
    p = parse_eft(PYFA_MUTATED)
    names = [(i.name, i.mutated) for i in p.items]
    assert names == [
        ("Mizuro's Modified Ballistic Control System", True),
        ("Caldari Navy Ballistic Control System", True),
        ("Missile Guidance Computer II", False),
        ("Corelum A-Type 10MN Afterburner", True),
        ("Caldari Navy Nova Light Missile", False),
    ]
    # the blocks are read, not warned about; [3] has none in this trimmed paste
    assert p.warnings == ("line 7: Corelum A-Type 10MN Afterburner [3] has no [3] block",)


def test_brackets_in_a_fit_name_and_zero_quantities():
    p = parse_eft("[Rifter, my [alt] fit]\nWarrior II x0\nWarrior II x2\n")
    assert p.ok and p.hull_name == "Rifter" and p.fit_name == "my [alt] fit"
    assert [(i.name, i.quantity) for i in p.items] == [("Warrior II", 2)]
    assert p.warnings == ("line 2: Warrior II x0 ignored",)
