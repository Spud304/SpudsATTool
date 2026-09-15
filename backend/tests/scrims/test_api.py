import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.scrims.models import Pilot, Session

pytestmark = pytest.mark.django_db
JSON = "application/json"


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type=JSON)


def patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type=JSON)


def put(client, url, body):
    return client.put(url, json.dumps(body), content_type=JSON)


def iso(dt):
    return dt.isoformat()


def test_permissions(client, imported_atxxii, login_as):
    tonight = timezone.now() + timedelta(hours=2)
    assert client.get("/api/scrims").status_code == 401
    login_as(character_id=5, name="Guest", role="guest")
    assert client.get("/api/scrims").status_code == 403
    client.get("/auth/logout")

    login_as(character_id=6, name="Viewer", role="viewer")
    assert client.get("/api/scrims").status_code == 200
    assert client.get("/api/pilots").status_code == 200
    assert post(client, "/api/scrims", {"title": "x", "date": iso(tonight)}).status_code == 403
    assert post(client, "/api/pilots", {"name": "x"}).status_code == 403
    client.get("/auth/logout")

    login_as(character_id=7, name="Cap", role="captain")
    resp = post(
        client, "/api/scrims", {"title": "OF 99", "date": iso(tonight), "stage_code": "bracket"}
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["ruleset"] == "ATXXII" and body["stage"] == "bracket" and body["can_manage"]
    assert body["can_rsvp"] and body["my_rsvp"] == "none"
    client.get("/auth/logout")

    login_as(character_id=6, name="Viewer", role="viewer")
    scrim = client.get(f"/api/scrims/{body['id']}").json()
    assert scrim["can_manage"] is False and scrim["can_rsvp"] is False and scrim["my_rsvp"] is None
    assert put(client, f"/api/scrims/{body['id']}/rsvp", {"rsvp": "yes"}).status_code == 403


def test_rsvp_tally_and_roll_call(client, imported_atxxii, login_as):
    tonight = timezone.now() + timedelta(hours=2)
    login_as(character_id=7, name="Cap", role="captain")
    scrim_id = post(client, "/api/scrims", {"title": "OF 99", "date": iso(tonight)}).json()["id"]
    client.get("/auth/logout")

    login_as(character_id=8, name="Spud", role="pilot")
    assert put(client, f"/api/scrims/{scrim_id}/rsvp", {"rsvp": "maybe"}).status_code == 422
    body = put(client, f"/api/scrims/{scrim_id}/rsvp", {"rsvp": "maybe", "reason": "late"}).json()
    assert body["my_rsvp"] == "maybe" and body["my_rsvp_reason"] == "late"
    me = next(a for a in body["attendance"] if a["is_me"])
    assert me["pilot_name"] == "Spud" and me["rsvp_reason"] == "late"
    assert body["attendance"][0]["pilot_name"] == "Spud"  # maybe sorts before no answer
    client.get("/auth/logout")

    login_as(character_id=7, name="Cap", role="captain")
    upcoming = client.get("/api/scrims").json()
    assert [s["id"] for s in upcoming] == [scrim_id]
    assert upcoming[0]["tally"] == {"yes": 0, "no": 0, "maybe": 1, "none": 1}
    assert client.get("/api/scrims", {"when": "past"}).json() == []
    assert client.get("/api/scrims", {"when": "later"}).status_code == 422

    spud = Pilot.objects.get(name="Spud")
    resp = patch(client, f"/api/scrims/{scrim_id}/attendance/{spud.pk}", {"attendance": "no_show"})
    assert resp.status_code == 422
    resp = patch(
        client,
        f"/api/scrims/{scrim_id}/attendance/{spud.pk}",
        {"attendance": "no_show", "reason": "never showed"},
    )
    assert resp.status_code == 200
    row = next(a for a in resp.json()["attendance"] if a["pilot_id"] == spud.pk)
    assert row["attendance"] == "no_show" and row["removed_reason"] == "never showed"
    assert AuditLog.objects.filter(action="scrim.no_show_removed", reason="never showed").exists()

    resp = post(client, f"/api/scrims/{scrim_id}/archive", {"reason": "cancelled"})
    assert resp.status_code == 200 and resp.json()["is_archived"]
    assert client.get("/api/scrims").json() == []
    assert [s["id"] for s in client.get("/api/scrims", {"when": "past"}).json()] == [scrim_id]


def test_roster_and_opponents_api(client, imported_atxxii, login_as):
    login_as(character_id=7, name="Cap", role="captain")
    resp = post(client, "/api/pilots", {"name": "Hired Gun", "is_merc": True, "roles_text": "Logi"})
    assert resp.status_code == 201 and resp.json()["is_merc"]
    pilot_id = resp.json()["id"]
    assert post(client, "/api/pilots", {"name": "hired gun"}).status_code == 409
    resp = patch(client, f"/api/pilots/{pilot_id}", {"status": "inactive", "notes": "gone"})
    assert resp.status_code == 200 and resp.json()["status"] == "inactive"
    assert patch(client, f"/api/pilots/{pilot_id}", {"status": "retired"}).status_code == 422
    names = {p["name"] for p in client.get("/api/pilots").json()}
    assert names == {"Cap", "Hired Gun"}
    assert [p["name"] for p in client.get("/api/pilots", {"status": "active"}).json()] == ["Cap"]

    resp = post(client, "/api/opponents", {"name": "Only Fleets", "notes": "kites"})
    assert resp.status_code == 201
    opp_id = resp.json()["id"]
    assert post(client, "/api/opponents", {"name": "Only Fleets"}).status_code == 409
    assert (
        patch(client, f"/api/opponents/{opp_id}", {"is_active": False}).json()["is_active"] is False
    )

    vocab = client.get("/api/scrims/vocab").json()
    assert "Red 1" in vocab["warp_labels"] and len(vocab["warp_labels"]) == 48
    assert [s["code"] for s in vocab["stages"]] == ["prelim", "bracket"]
    assert vocab["active_ruleset"] == "ATXXII" and "practice" in vocab["kinds"]

    tonight = timezone.now() + timedelta(hours=2)
    resp = post(
        client, "/api/scrims", {"title": "OF 99", "date": iso(tonight), "opponent_id": opp_id}
    )
    assert resp.status_code == 201 and resp.json()["opponent_name"] == "Only Fleets"
    resp = patch(
        client, f"/api/scrims/{resp.json()['id']}", {"title": "OF 100", "motd": "be there"}
    )
    assert resp.json()["title"] == "OF 100" and resp.json()["motd"] == "be there"
    assert Session.objects.count() == 1
