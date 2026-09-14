from dataclasses import replace

import pytest

from apps.accounts.models import Membership, MembershipSource, MembershipStatus, Role, User
from apps.audit.models import AuditLog
from apps.core.importing import ImportReport
from apps.library import comps, services
from apps.library.comps import SlotPatch
from apps.library.models import Comp, CompStatus
from apps.rules import adapters
from apps.rules.importer import import_ruleset
from apps.rules.models import PointTableVersion
from apps.rules.yaml_io import load_ruleset_document
from tests.conftest import ABSO_FIT, ABSO_PYFA, MINI_ATXXII
from tests.rules.engine import atxxii as at

pytestmark = pytest.mark.django_db


def make_user(character_id: int, role: str) -> User:
    user = User.objects.create(username=f"char:{character_id}", display_name=f"U{character_id}")
    Membership.objects.create(
        user=user, role=role, status=MembershipStatus.ACTIVE, source=MembershipSource.EXPLICIT
    )
    return user


@pytest.fixture
def pilot(db):
    return make_user(1, Role.PILOT)


@pytest.fixture
def theo(db):
    return make_user(2, Role.THEORYCRAFTER)


def of99_slots(overrides: dict | None = None) -> list[SlotPatch]:
    overrides = overrides or {}
    out = []
    for i, type_id in enumerate(at.OF99_SET1, start=1):
        out.append(replace(SlotPatch(slot_no=i, type_id=type_id), **overrides.get(i, {})))
    return out


def test_create_forced_suggested(library_sde, imported_atxxii, pilot):
    with pytest.raises(comps.CompError) as exc:
        comps.create_comp(pilot, name="Test comp", status="active")
    assert exc.value.status == 403
    comp = comps.create_comp(pilot, name="  Test comp ")
    assert comp.status == CompStatus.SUGGESTED and comp.name == "Test comp"
    assert comp.ruleset.code == "ATXXII"  # active ruleset default
    assert [s.slot_no for s in comp.slots.all()] == list(range(1, 11))
    assert AuditLog.objects.filter(action="comp.created").count() == 1
    with pytest.raises(comps.CompError) as dup:
        comps.create_comp(pilot, name="test COMP")
    assert dup.value.status == 409


def test_full_slot_replacement_evaluates(library_sde, imported_atxxii, theo):
    comp = comps.create_comp(theo, name="OF99", status="construction")
    assert comp.reviewed_by == theo
    comps.update_comp(theo, comp, slots=of99_slots())
    ev = comps.evaluate(comp)
    assert ev is not None and ev.total_points == 200 and ev.cap_status == "EXACT" and ev.is_legal
    entry = AuditLog.objects.get(action="comp.updated")
    assert entry.after["slots_changed"] == list(range(1, 11))
    # unchanged replacement records nothing new
    comps.update_comp(theo, comp, slots=of99_slots())
    assert AuditLog.objects.filter(action="comp.updated").count() == 1


def test_default_fit_must_match_ship_and_drives_links(library_sde, imported_atxxii, theo):
    fit = services.create_fit(theo, eft_text=ABSO_FIT, pyfa_summary=ABSO_PYFA, status="active")
    comp = comps.create_comp(theo, name="Links")
    with pytest.raises(comps.CompError) as exc:
        comps.update_comp(theo, comp, slots=of99_slots({1: {"default_fit_id": fit.pk}}))
    assert exc.value.status == 422 and "Absolution" in str(exc.value)
    comps.update_comp(theo, comp, slots=of99_slots({3: {"default_fit_id": fit.pk}}))
    ev = comps.evaluate(comp)
    assert ev is not None
    assert ev.slots[2].has_links and ev.slots[2].link_index == 1
    stats = comps.comp_stats(comp)
    assert stats["fits_set"] == 1 and stats["dps_total"] == 709 and stats["speed_min"] == 1230


def test_link_scripts_validation(library_sde, imported_atxxii, theo):
    comp = comps.create_comp(theo, name="Scripts")
    for bad in (("XX",), ("AE", "AE"), ("AE", "AR", "RR", "SH", "SE", "AS")):
        with pytest.raises(comps.CompError) as exc:
            comps.update_comp(theo, comp, slots=of99_slots({1: {"link_scripts": bad}}))
        assert exc.value.status == 422
    comps.update_comp(theo, comp, slots=of99_slots({1: {"link_scripts": ("AE", "AR", "RR")}}))
    ev = comps.evaluate(comp)
    assert ev is not None and ev.slots[0].has_links  # scripts without a fit still count as links


def test_slot_shape_and_bad_ship(library_sde, imported_atxxii, theo):
    comp = comps.create_comp(theo, name="Shape")
    with pytest.raises(comps.CompError):
        comps.update_comp(theo, comp, slots=of99_slots()[:9])
    dup = of99_slots()
    dup[1] = SlotPatch(slot_no=1, type_id=at.ASTARTE)
    with pytest.raises(comps.CompError):
        comps.update_comp(theo, comp, slots=dup)
    with pytest.raises(comps.CompError) as exc:
        comps.update_comp(theo, comp, slots=of99_slots({1: {"type_id": 990007}}))
    assert "unknown hull" in str(exc.value)
    with pytest.raises(comps.CompError):
        comps.update_comp(theo, comp, slots=of99_slots({1: {"warp_in_km": 5000}}))


def test_status_change_permissions(library_sde, imported_atxxii, pilot, theo):
    comp = comps.create_comp(pilot, name="Mine")
    with pytest.raises(comps.CompError) as exc:
        comps.update_comp(pilot, comp, status="active")
    assert exc.value.status == 403
    comps.update_comp(theo, comp, status="active", reason="solid")
    comp.refresh_from_db()
    assert comp.status == "active" and comp.reviewed_by == theo and comp.reviewed_at
    entry = AuditLog.objects.get(action="comp.status_changed")
    assert entry.reason == "solid" and entry.after == {"status": "active"}


def test_clone_same_and_smaller_ruleset(library_sde, imported_atxxii, theo):
    comp = comps.create_comp(theo, name="Source", status="active", notes="n", ban_theory="b")
    comps.update_comp(theo, comp, slots=of99_slots({1: {"warp_in_km": 40, "ship_note": "x"}}))
    copy = comps.clone_comp(theo, comp)
    assert copy.name == "Source (copy)" and copy.status == "active" and copy.notes == "n"
    assert [s.ship_id for s in copy.slots.all()] == list(at.OF99_SET1)
    assert copy.slots.get(slot_no=1).warp_in_km == 40
    assert AuditLog.objects.filter(action="comp.cloned").exists()

    small = load_ruleset_document(
        MINI_ATXXII.replace("code: ATXXII", "code: ATX2").replace(
            "fielded_pilots: 10", "fielded_pilots: 5"
        )
    )
    other = import_ruleset(small, report=ImportReport(source="small"))
    moved = comps.clone_comp(theo, comp, name="Moved", ruleset=other)
    assert moved.ruleset == other and moved.slots.count() == 5
    assert [s.ship_id for s in moved.slots.all()] == list(at.OF99_SET1[:5])


def test_evaluate_without_point_table(library_sde, imported_atxxii, theo):
    comp = comps.create_comp(theo, name="No table")
    PointTableVersion.objects.filter(ruleset=comp.ruleset).update(is_current=False)
    adapters.clear_cache()
    comp.ruleset.refresh_from_db()
    assert comps.evaluate(comp) is None
    assert comps.comp_stats(comp)["dps_total"] is None


def test_archetypes_seeded_and_editable(db, theo):
    from apps.library.models import Archetype

    assert (
        Archetype.objects.count() == 16 and Archetype.objects.filter(is_retired=True).count() == 2
    )
    a = comps.create_archetype(theo, name="Bait")
    comps.update_archetype(theo, a, is_retired=True)
    assert Archetype.objects.get(name="Bait").is_retired
    with pytest.raises(comps.CompError):
        comps.create_archetype(theo, name="Rush")
    assert Comp.objects.count() == 0
