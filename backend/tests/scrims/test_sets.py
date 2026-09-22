import threading
from typing import cast

import pytest
from django.db import connection

from apps.audit.models import AuditLog
from apps.scrims import broker, sets
from apps.scrims.broker import MemoryBroker
from apps.scrims.models import Assignment, Ban, ChangeEvent, Pilot, Round, Set
from apps.scrims.roster import ScrimError
from tests.rules.engine import atxxii as at

pytestmark = pytest.mark.django_db


def slot(doc: dict, round_no: int, side: str, slot_no: int) -> dict:
    rnd = next(r for r in doc["rounds"] if r["round_no"] == round_no)
    return next(s for s in rnd[side]["slots"] if s["slot_no"] == slot_no)


def test_create_set_prepares_bans_round_and_slots(
    scrim, captain, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        doc = sets.create_set(captain, scrim.pk, label="Armor Rush")
    the_set = Set.objects.get(pk=doc["id"])
    assert the_set.index == 1 and the_set.our_side == "A" and doc["label"] == "Armor Rush"
    assert Ban.objects.filter(set=the_set, kind="standard").count() == 8
    assert Round.objects.filter(set=the_set).count() == 1
    assert Assignment.objects.filter(round__set=the_set).count() == 20
    # Chips follow the stage's ABBAABAB order, ours (team A) marked.
    assert [c["order"] for c in doc["bans"]] == list(range(1, 9))
    assert [c["side"] for c in doc["bans"]] == list("ABBAABAB")
    assert [c["is_ours"] for c in doc["bans"]][:3] == [True, False, False]
    assert doc["bans_per_side"] == 4 and doc["avalanche_enabled"] and doc["avalanche_bans"] == []
    assert doc["rounds"][0]["us"]["total_points"] == 0 and doc["record"] == {
        "wins": 0,
        "losses": 0,
        "draws": 0,
    }
    event = ChangeEvent.objects.get(session=scrim)
    assert event.seq == 1 and event.kind == "set" and event.payload["set"]["id"] == doc["id"]
    assert AuditLog.objects.filter(action="set.created").exists()
    published = cast(MemoryBroker, broker.get_broker()).published
    assert published and published[-1][1]["seq"] == 1


def test_second_set_copies_the_previous_lineup(scrim, captain, theo, of99_comp):
    first = sets.create_set(captain, scrim.pk)
    sets.patch_set(theo, scrim.pk, first["id"], comp_id=of99_comp.pk, warp_calls=["A", "B"])
    who = Pilot.objects.get(name="Pilot One")
    sets.patch_assignment(theo, scrim.pk, first["id"], 1, "US", 1, pilot_id=who.pk, died=True)
    second = sets.create_set(captain, scrim.pk)
    assert second["index"] == 2 and second["comp_id"] == of99_comp.pk
    assert second["warp_calls"] == ["A", "B"]
    copied = slot(second, 1, "us", 1)
    assert copied["pilot_id"] == who.pk and copied["type_id"] == at.ASTARTE and not copied["died"]
    assert all(c["type_id"] is None for c in second["bans"])  # bans start empty
    blank = sets.create_set(captain, scrim.pk, copy_previous=False)
    assert blank["comp_id"] is None and slot(blank, 1, "us", 1)["type_id"] is None


def test_load_comp_and_the_override_rule(scrim, captain, theo, of99_comp, abso_fit):
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    doc = sets.patch_set(theo, scrim.pk, set_id, comp_id=of99_comp.pk)
    assert doc["comp_name"] == "Armor Rush"
    us = doc["rounds"][0]["us"]
    assert us["total_points"] == 200 and us["is_legal"] and us["cap_status"] == "EXACT"
    three = slot(doc, 1, "us", 3)
    assert three["type_id"] == at.ABSOLUTION and three["fit_id"] == abso_fit.pk
    assert three["fit_text"].startswith("[Absolution") and three["repeat_note"] == "info bursts"
    assert three["link_scripts"] == ["AE"] and three["load_default"] and three["has_links"]
    assert three["link_index"] == 1

    # Pilot and warp-in survive an override; the comp's dependent defaults do not.
    who = Pilot.objects.get(name="Pilot One")
    sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 3, pilot_id=who.pk, warp_in_km=40)
    doc = sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 3, type_id=at.ZEALOT)
    three = slot(doc, 1, "us", 3)
    assert (
        three["type_id"] == at.ZEALOT and three["pilot_id"] == who.pk and three["warp_in_km"] == 40
    )
    assert three["fit_id"] is None and three["fit_text"] == "" and three["repeat_note"] == ""
    assert three["link_scripts"] == [] and not three["load_default"]
    assert doc["rounds"][0]["us"]["total_points"] == 200 - 33 + 21 + 4  # two Zealots: +2 each

    # Re-ticking load_default brings the comp's slot back.
    doc = sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 3, load_default=True)
    three = slot(doc, 1, "us", 3)
    assert three["type_id"] == at.ABSOLUTION and three["fit_id"] == abso_fit.pk
    assert three["repeat_note"] == "info bursts" and three["pilot_id"] == who.pk

    # A fit for another hull is refused; clearing the comp keeps the lineup as plain fields.
    with pytest.raises(ScrimError) as exc:
        sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 4, fit_id=abso_fit.pk)
    assert exc.value.status == 422
    doc = sets.patch_set(theo, scrim.pk, set_id, comp_id=None)
    assert doc["comp_id"] is None and slot(doc, 1, "us", 3)["fit_id"] == abso_fit.pk


def test_rounds_copy_forward_and_deaths_score(scrim, captain, theo, of99_comp):
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    sets.patch_set(theo, scrim.pk, set_id, comp_id=of99_comp.pk)
    doc = sets.paste_opp_lineup(
        theo,
        scrim.pk,
        set_id,
        1,
        "Astarte\nAstarte\nAbsolution, Zealot\nAshimmu\nAugoror Navy Issue\nKeres\nDeacon\nDeacon\nMaulus",
    )[0]
    assert doc["rounds"][0]["opp"]["total_points"] == 200
    doc = sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 1, died=True)
    doc = sets.patch_assignment(theo, scrim.pk, set_id, 1, "OPP", 10, died=True)
    score = doc["rounds"][0]["score"]
    assert (
        doc["rounds"][0]["us"]["points_lost"] == 36 and doc["rounds"][0]["opp"]["points_lost"] == 7
    )
    assert score["differential"] == 7 - 36 and score["leader"] == "OPP"
    assert score["us"]["handicap_conceded"] == 0

    doc = sets.add_round(theo, scrim.pk, set_id)
    assert [r["round_no"] for r in doc["rounds"]] == [1, 2]
    two = slot(doc, 2, "us", 1)
    assert two["type_id"] == at.ASTARTE and not two["died"]  # lineup copied, deaths reset
    assert doc["rounds"][1]["score"]["differential"] == 0

    with pytest.raises(ScrimError):
        sets.delete_round(captain, scrim.pk, set_id, 1)  # only the last round goes
    doc = sets.delete_round(captain, scrim.pk, set_id, 2)
    assert len(doc["rounds"]) == 1
    with pytest.raises(ScrimError):
        sets.delete_round(captain, scrim.pk, set_id, 1)  # a set keeps round 1


def test_outcome_pre_creates_avalanche_chips_that_apply_from_the_next_round(
    scrim, captain, theo, of99_comp
):
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    sets.patch_set(theo, scrim.pk, set_id, comp_id=of99_comp.pk)
    doc = sets.patch_round(
        theo, scrim.pk, set_id, 1, outcome="loss"
    )  # we are A and lost: A bans 2, B bans 1
    chips = doc["avalanche_bans"]
    assert [(c["side"], c["in_effect_from_round"]) for c in chips] == [("A", 2), ("A", 2), ("B", 2)]
    assert doc["record"] == {"wins": 0, "losses": 1, "draws": 0}

    doc = sets.put_ban(
        theo,
        scrim.pk,
        set_id,
        side="A",
        kind="avalanche",
        index=1,
        type_id=at.ASHIMMU,
        in_effect_from_round=2,
    )
    assert doc["rounds"][0]["banned_type_ids"] == []  # round 1 already fought
    doc = sets.add_round(theo, scrim.pk, set_id)
    assert doc["rounds"][1]["banned_type_ids"] == [at.ASHIMMU]
    assert slot(doc, 2, "us", 5)["is_banned"] and not slot(doc, 1, "us", 5)["is_banned"]
    assert not doc["rounds"][1]["us"]["is_legal"]

    # Flipping the outcome swaps the empty chips but keeps the recorded hull.
    doc = sets.patch_round(theo, scrim.pk, set_id, 1, outcome="win")
    chips = doc["avalanche_bans"]
    assert [(c["side"], c["type_id"]) for c in chips] == [
        ("A", at.ASHIMMU),
        ("B", None),
        ("B", None),
    ]

    # Standard bans: order is enforced by index, and a hull outside the ruleset is refused.
    doc = sets.put_ban(
        theo, scrim.pk, set_id, side="B", kind="standard", index=1, type_id=at.ASTARTE
    )
    assert doc["bans"][1]["type_id"] == at.ASTARTE and doc["bans"][1]["order"] == 2
    assert slot(doc, 1, "us", 1)["is_banned"]
    with pytest.raises(ScrimError):
        sets.put_ban(theo, scrim.pk, set_id, side="A", kind="standard", index=5, type_id=at.ASTARTE)
    with pytest.raises(ScrimError):
        sets.put_ban(theo, scrim.pk, set_id, side="A", kind="standard", index=1, type_id=999999)


def test_paste_reports_unknown_hulls_and_clears_the_rest(scrim, captain, theo):
    doc = sets.create_set(captain, scrim.pk)
    doc, unresolved = sets.paste_opp_lineup(
        theo, scrim.pk, doc["id"], 1, "Astarte\nNotAShip\nkeres"
    )
    opp = doc["rounds"][0]["opp"]["slots"]
    assert [s["type_id"] for s in opp[:3]] == [at.ASTARTE, None, at.KERES]
    assert unresolved == ["NotAShip"]


def test_link_scripts_and_pilot_rules(scrim, captain, theo):
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    with pytest.raises(ScrimError):
        sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 1, link_scripts=["ZZ"])
    with pytest.raises(ScrimError):
        sets.patch_assignment(
            theo, scrim.pk, set_id, 1, "OPP", 1, pilot_id=Pilot.objects.get(name="Pilot One").pk
        )
    doc = sets.patch_assignment(
        theo, scrim.pk, set_id, 1, "US", 1, link_scripts=["AE", "SH"], type_id=at.ASTARTE
    )
    one = slot(doc, 1, "us", 1)
    assert one["link_scripts"] == ["AE", "SH"] and one["has_links"] and one["link_index"] == 1


def test_delete_set_emits_and_audits(scrim, captain):
    doc = sets.create_set(captain, scrim.pk)
    sets.delete_set(captain, scrim.pk, doc["id"], "misclick")
    assert not Set.objects.filter(pk=doc["id"]).exists()
    last = ChangeEvent.objects.get(session=scrim, seq=2)
    assert last.kind == "set_deleted" and last.payload == {"set_id": doc["id"]} and last.seq == 2
    assert AuditLog.objects.filter(action="set.deleted", reason="misclick").exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_edits_serialise_on_the_session_lock(scrim, captain, theo):
    scrim.refresh_from_db()
    start = scrim.event_seq  # members admitted after the scrim already put attendance events here
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    errors: list[Exception] = []

    def edit(slot_no: int) -> None:
        try:
            sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", slot_no, type_id=at.ASTARTE)
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=edit, args=(n,)) for n in range(1, 7)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    seqs = list(
        ChangeEvent.objects.filter(session=scrim).order_by("seq").values_list("seq", flat=True)
    )
    assert seqs[-7:] == list(range(start + 1, start + 8))  # create + six edits, no gaps
    scrim.refresh_from_db()
    assert scrim.event_seq == start + 7


def test_the_same_pilot_in_two_slots_is_an_error(scrim, captain, theo, of99_comp):
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    sets.patch_set(theo, scrim.pk, set_id, comp_id=of99_comp.pk)
    who = Pilot.objects.get(name="Pilot One")
    sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 2, pilot_id=who.pk)
    doc = sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 5, pilot_id=who.pk)
    us = doc["rounds"][0]["us"]
    assert not us["is_legal"]
    dup = next(v for v in us["violations"] if v["code"] == "DUPLICATE_PILOT")
    assert dup["slot_nos"] == [2, 5] and "Pilot One" in dup["message"]
    assert "DUPLICATE_PILOT" in slot(doc, 1, "us", 2)["flags"]
    assert "DUPLICATE_PILOT" in slot(doc, 1, "us", 5)["flags"]
    doc = sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 5, pilot_id=None)
    assert doc["rounds"][0]["us"]["is_legal"]


def test_an_archived_scrim_is_read_only(scrim, captain, pilot):
    from apps.scrims import sessions

    doc = sets.create_set(captain, scrim.pk)
    sessions.archive_session(captain, scrim, "done")
    scrim.refresh_from_db()
    edits = [
        lambda: sets.create_set(captain, scrim.pk),
        lambda: sets.patch_set(captain, scrim.pk, doc["id"], label="late edit"),
        lambda: sets.add_round(captain, scrim.pk, doc["id"]),
        lambda: sets.delete_set(captain, scrim.pk, doc["id"]),
        lambda: sessions.update_session(captain, scrim, title="renamed"),
        lambda: sessions.set_attendance(captain, scrim, Pilot.objects.get(user=pilot), "attended"),
    ]
    for edit in edits:
        with pytest.raises(ScrimError) as err:
            edit()
        assert err.value.status == 409
