import json

import pytest

from apps.accounts import roles
from apps.scrims import sets
from apps.scrims.models import Pilot
from tests.rules.engine import atxxii as at

pytestmark = pytest.mark.django_db
JSON = "application/json"


def call(client, method, url, body=None):
    fn = getattr(client, method)
    if body is None:
        return fn(url)
    return fn(url, json.dumps(body), content_type=JSON)


def slot(doc, round_no, side, slot_no):
    rnd = next(r for r in doc["rounds"] if r["round_no"] == round_no)
    return next(s for s in rnd[side]["slots"] if s["slot_no"] == slot_no)


@pytest.fixture
def api_scrim(scrim, of99_comp):
    return scrim


def test_set_lifecycle_over_the_api(client, api_scrim, of99_comp, login_as):
    base = f"/api/scrims/{api_scrim.pk}"
    login_as(character_id=6, name="Viewer", role="viewer")
    assert call(client, "post", f"{base}/sets", {}).status_code == 403
    client.get("/auth/logout")

    login_as(character_id=7, name="Cap", role="captain")
    resp = call(client, "post", f"{base}/sets", {"label": "Armor Rush"})
    assert resp.status_code == 201, resp.content
    doc = resp.json()
    set_id = doc["id"]
    assert len(doc["bans"]) == 8 and doc["rounds"][0]["us"]["slots"][0]["slot_no"] == 1

    resp = call(
        client,
        "patch",
        f"{base}/sets/{set_id}",
        {"comp_id": of99_comp.pk, "warp_calls": ["A", "Red 2", "C", "1"]},
    )
    assert resp.status_code == 200 and resp.json()["rounds"][0]["us"]["total_points"] == 200
    assert resp.json()["warp_calls"] == ["A", "Red 2", "C", "1"]

    resp = call(
        client,
        "post",
        f"{base}/sets/{set_id}/bans",
        {"side": "B", "index": 1, "type_id": at.ASTARTE},
    )
    assert resp.status_code == 200 and resp.json()["bans"][1]["ship_name"] == "Astarte"
    assert slot(resp.json(), 1, "us", 1)["is_banned"]

    resp = call(
        client, "post", f"{base}/sets/{set_id}/rounds/1/opp-lineup", {"text": "Astarte\nNope"}
    )
    assert resp.status_code == 200 and resp.json()["unresolved"] == ["Nope"]
    assert slot(resp.json()["set"], 1, "opp", 1)["type_id"] == at.ASTARTE

    resp = call(client, "patch", f"{base}/sets/{set_id}/rounds/1/US/1", {"died": True})
    assert resp.status_code == 200 and resp.json()["rounds"][0]["us"]["points_lost"] == 36
    resp = call(
        client,
        "patch",
        f"{base}/sets/{set_id}/rounds/1",
        {"outcome": "loss", "notes": "lost the Astarte"},
    )
    assert resp.status_code == 200 and resp.json()["record"]["losses"] == 1
    assert len(resp.json()["avalanche_bans"]) == 3

    resp = call(client, "post", f"{base}/sets/{set_id}/rounds")
    assert resp.status_code == 201 and len(resp.json()["rounds"]) == 2
    resp = call(client, "delete", f"{base}/sets/{set_id}/rounds/2")
    assert resp.status_code == 200 and len(resp.json()["rounds"]) == 1

    full = client.get(base).json()
    assert [s["id"] for s in full["sets"]] == [set_id] and full["event_seq"] >= 7
    assert full["sets"][0]["rounds"][0]["outcome"] == "loss"

    resp = call(client, "delete", f"{base}/sets/{set_id}", {"reason": "done"})
    assert resp.status_code == 204
    assert client.get(base).json()["sets"] == []


def test_pilot_may_touch_only_their_slot_and_deaths(
    client, api_scrim, of99_comp, abso_fit, login_as, captain, theo
):
    base = f"/api/scrims/{api_scrim.pk}"
    doc = sets.create_set(captain, api_scrim.pk)
    set_id = doc["id"]
    sets.patch_set(theo, api_scrim.pk, set_id, comp_id=of99_comp.pk)

    login_as(character_id=8, name="Spud", role="pilot")
    me = client.get("/api/me").json()
    mine = Pilot.objects.get(user_id=me["user_id"])
    other = Pilot.objects.get(name="Pilot One")
    sets.patch_assignment(theo, api_scrim.pk, set_id, 1, "US", 3, pilot_id=mine.pk)
    sets.patch_assignment(theo, api_scrim.pk, set_id, 1, "US", 4, pilot_id=other.pk)

    url = f"{base}/sets/{set_id}/rounds/1/US"
    assert call(client, "patch", f"{url}/3", {"custom_note": "stay close"}).status_code == 200
    assert call(client, "patch", f"{url}/3", {"fit_id": abso_fit.pk}).status_code == 200
    resp = call(client, "patch", f"{url}/3", {"type_id": at.ZEALOT})
    assert resp.status_code == 403 and "type_id" in resp.json()["detail"]
    assert call(client, "patch", f"{url}/4", {"custom_note": "not mine"}).status_code == 403
    assert (
        call(client, "patch", f"{url}/4", {"died": True}).status_code == 200
    )  # pilots_can_score default
    assert (
        call(client, "patch", f"{base}/sets/{set_id}/rounds/1", {"outcome": "win"}).status_code
        == 200
    )
    assert (
        call(
            client,
            "post",
            f"{base}/sets/{set_id}/bans",
            {"side": "A", "index": 1, "type_id": at.ASTARTE},
        ).status_code
        == 403
    )
    assert call(client, "post", f"{base}/sets/{set_id}/rounds").status_code == 403
    assert call(client, "patch", f"{base}/sets/{set_id}", {"label": "x"}).status_code == 403

    pilot_role = roles.by_slug("pilot")
    pilot_role.permissions = [p for p in pilot_role.permissions if p != "score"]
    pilot_role.save()
    assert call(client, "patch", f"{url}/4", {"died": False}).status_code == 403
    assert (
        call(client, "patch", f"{base}/sets/{set_id}/rounds/1", {"outcome": "loss"}).status_code
        == 403
    )
    assert call(client, "patch", f"{url}/3", {"custom_note": "still mine"}).status_code == 200


def test_guest_sees_only_scrims_they_fly_in(client, api_scrim, login_as, captain, theo):
    base = f"/api/scrims/{api_scrim.pk}"
    doc = sets.create_set(captain, api_scrim.pk)
    login_as(character_id=11, name="Merc Guest", role="guest")
    assert client.get(base).status_code == 403
    assert call(client, "post", f"{base}/presence", {"focus": None}).status_code == 403

    me = client.get("/api/me").json()
    merc = Pilot.objects.get(user_id=me["user_id"])  # guests can fly, so admission made the row
    sets.patch_assignment(theo, api_scrim.pk, doc["id"], 1, "US", 7, pilot_id=merc.pk)
    resp = client.get(base)
    assert (
        resp.status_code == 200
        and slot(resp.json()["sets"][0], 1, "us", 7)["pilot_user_id"] == me["user_id"]
    )
    resp = call(client, "post", f"{base}/presence", {"focus": "us.7.fit"})
    assert resp.status_code == 200 and resp.json()[0]["name"] == "Merc Guest"
    assert call(client, "delete", f"{base}/presence").json() == []
