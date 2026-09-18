import json

import pytest

from apps.audit.models import AuditLog
from apps.scrims import events, sets
from apps.scrims.history import history_document
from apps.scrims.models import ChangeEvent, Round, Set
from apps.scrims.roster import ScrimError
from apps.scrims.sessions import scope

pytestmark = pytest.mark.django_db


def test_deleted_set_is_hidden_and_comes_back_with_the_same_id(scrim, captain, theo, of99_comp):
    doc = sets.create_set(captain, scrim.pk)
    sets.patch_set(theo, scrim.pk, doc["id"], comp_id=of99_comp.pk)
    sets.delete_set(captain, scrim.pk, doc["id"], "misclick")
    assert not Set.objects.filter(pk=doc["id"]).exists()
    assert Set.all_objects.get(pk=doc["id"]).deleted_by == captain
    assert scrim.sets.count() == 0

    history = history_document(scrim)
    assert [d["id"] for d in history["deleted_sets"]] == [doc["id"]]
    assert history["deleted_sets"][0]["comp_name"] == "Armor Rush"
    assert [e["action"] for e in history["entries"]][:2] == ["set.deleted", "set.created"]
    assert (
        AuditLog.objects.filter(scope=scope(scrim)).count() == 3
    )  # created scrim, created set, deleted set

    restored = sets.restore_set(captain, scrim.pk, doc["id"])
    assert restored["id"] == doc["id"] and restored["comp_name"] == "Armor Rush"
    assert scrim.sets.count() == 1
    assert AuditLog.objects.filter(action="set.restored", scope=scope(scrim)).exists()
    with pytest.raises(ScrimError):
        sets.restore_set(captain, scrim.pk, doc["id"])  # nothing left to restore


def test_new_set_at_the_same_index_purges_the_deleted_one(scrim, captain):
    first = sets.create_set(captain, scrim.pk)
    sets.delete_set(captain, scrim.pk, first["id"])
    second = sets.create_set(captain, scrim.pk)
    assert second["index"] == 1
    assert not Set.all_objects.filter(pk=first["id"]).exists()
    assert history_document(scrim)["deleted_sets"] == []


def test_round_soft_delete_and_restore_rules(scrim, captain, theo):
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    sets.patch_round(theo, scrim.pk, set_id, 1, outcome="win")
    sets.add_round(theo, scrim.pk, set_id)
    sets.patch_round(theo, scrim.pk, set_id, 2, outcome="loss")
    doc = sets.add_round(theo, scrim.pk, set_id)
    assert [r["round_no"] for r in doc["rounds"]] == [1, 2, 3]

    doc = sets.delete_round(captain, scrim.pk, set_id, 3)
    assert [r["round_no"] for r in doc["rounds"]] == [1, 2]
    assert Round.all_objects.filter(set_id=set_id, round_no=3, deleted_at__isnull=False).exists()
    history = history_document(scrim)
    assert (
        history["deleted_rounds"][0]["round_no"] == 3 and history["deleted_rounds"][0]["restorable"]
    )

    # Delete round 2 too: round 3 now has a live round below it missing, and round 2 is the newer deletion.
    sets.delete_round(captain, scrim.pk, set_id, 2)
    rounds = {r["round_no"]: r["restorable"] for r in history_document(scrim)["deleted_rounds"]}
    assert rounds == {2: True, 3: True}
    doc = sets.restore_round(captain, scrim.pk, set_id, 2)
    assert [r["round_no"] for r in doc["rounds"]] == [1, 2] and doc["rounds"][1][
        "outcome"
    ] == "loss"

    # Adding a fresh round 3 purges the deleted one; restoring it afterwards is refused.
    doc = sets.add_round(theo, scrim.pk, set_id)
    assert [r["round_no"] for r in doc["rounds"]] == [1, 2, 3]
    assert not Round.all_objects.filter(
        set_id=set_id, round_no=3, deleted_at__isnull=False
    ).exists()
    with pytest.raises(ScrimError):
        sets.restore_round(captain, scrim.pk, set_id, 3)

    # A deleted round below a live one cannot come back until the live one goes.
    sets.delete_round(captain, scrim.pk, set_id, 3)
    sets.add_round(theo, scrim.pk, set_id)  # new live 3, purges the deleted 3
    sets.patch_round(theo, scrim.pk, set_id, 3, outcome="win")
    sets.add_round(theo, scrim.pk, set_id)  # live 4
    sets.delete_round(captain, scrim.pk, set_id, 4)
    sets.delete_round(captain, scrim.pk, set_id, 3)
    sets.add_round(theo, scrim.pk, set_id)  # purges deleted 3, live 3 again; deleted 4 remains
    entry = next(r for r in history_document(scrim)["deleted_rounds"] if r["round_no"] == 4)
    assert entry["restorable"]  # nothing newer than 4 is live
    sets.patch_round(theo, scrim.pk, set_id, 3, outcome="win")
    sets.add_round(theo, scrim.pk, set_id)  # purges deleted 4
    assert history_document(scrim)["deleted_rounds"] == []


def test_emit_prunes_the_replay_buffer(scrim, captain):
    for _ in range(505):
        events.notify(scrim.pk, events.KIND_SESSION, captain)
    seqs = list(
        ChangeEvent.objects.filter(session=scrim).order_by("seq").values_list("seq", flat=True)
    )
    assert seqs[0] == 5 and seqs[-1] == 505 and len(seqs) == 501


def test_history_api_permissions(client, scrim, captain, login_as):
    doc = sets.create_set(captain, scrim.pk)
    sets.delete_set(captain, scrim.pk, doc["id"], "oops")
    base = f"/api/scrims/{scrim.pk}"

    login_as(character_id=6, name="Viewer", role="viewer")
    resp = client.get(f"{base}/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted_sets"][0]["id"] == doc["id"]
    assert body["entries"][0]["action"] == "set.deleted" and body["entries"][0]["reason"] == "oops"
    assert client.post(f"{base}/sets/{doc['id']}/restore").status_code == 403
    client.get("/auth/logout")

    login_as(character_id=5, name="Guest", role="guest")
    assert client.get(f"{base}/history").status_code == 403
    client.get("/auth/logout")

    login_as(character_id=7, name="Cap", role="captain")
    resp = client.post(f"{base}/sets/{doc['id']}/restore")
    assert resp.status_code == 200 and resp.json()["id"] == doc["id"]
    assert client.get(f"{base}/history").json()["deleted_sets"] == []
    assert client.get(base).json()["sets"][0]["id"] == doc["id"]
    assert (
        client.post(
            f"{base}/sets/{doc['id']}/rounds/2/restore",
            json.dumps({}),
            content_type="application/json",
        ).status_code
        == 404
    )
