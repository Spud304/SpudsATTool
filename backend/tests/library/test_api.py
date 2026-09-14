import json

import pytest

from apps.audit.models import AuditLog
from apps.core.models import Team
from apps.library.models import Fit

from .conftest import ABSO_FIT, ABSO_PYFA

pytestmark = pytest.mark.django_db

JSON = "application/json"


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type=JSON)


def patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type=JSON)


def test_anonymous_and_viewer(client, library_sde, login_as):
    assert client.get("/api/fits").status_code == 401
    login_as(role="viewer")
    assert client.get("/api/fits").status_code == 403
    assert post(client, "/api/fits/parse", {"eft_text": ABSO_FIT}).status_code == 403


def test_pilot_browsing_can_be_switched_off(client, library_sde, login_as):
    login_as(role="pilot")
    assert client.get("/api/fits").status_code == 200
    team = Team.get_solo()
    team.pilots_can_browse_library = False
    team.save()
    assert client.get("/api/fits").status_code == 403
    assert client.get("/api/me").json()["capabilities"]["browse_library"] is False


def test_parse_preview(client, library_sde, login_as):
    login_as()
    body = post(
        client,
        "/api/fits/parse",
        {"eft_text": ABSO_FIT + "Mystery Module\n", "pyfa_summary": ABSO_PYFA},
    ).json()
    assert body["ok"] and body["hull_type_id"] == 22448 and body["fit_name"] == "Octo Ewar Abso"
    assert body["unresolved"] == ["Mystery Module"] and body["has_links"]
    assert body["stats"]["dps"] == 709 and body["stats"]["ok"]
    laser = next(i for i in body["items"] if i["name"] == "Heavy Beam Laser II")
    assert laser["meta_group_name"] == "Tech II" and laser["charge_type_id"] == 990011
    bad = post(client, "/api/fits/parse", {"eft_text": "[Nope, x]\nStasis Webifier II"}).json()
    assert not bad["ok"] and "unknown hull" in bad["errors"][0]


def test_pilot_create_is_forced_to_suggested(client, library_sde, login_as):
    login_as(character_id=1, role="pilot")
    resp = post(client, "/api/fits", {"eft_text": ABSO_FIT, "status": "active"})
    assert resp.status_code == 403
    resp = post(client, "/api/fits", {"eft_text": ABSO_FIT, "pyfa_summary": ABSO_PYFA})
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["status"] == "suggested" and body["can_edit"] and body["created_by_name"] == "Pilot"
    assert body["ehp_k"] == 97.6 and body["has_links"]
    assert post(client, "/api/fits", {"eft_text": ABSO_FIT}).status_code == 409


def test_pilot_edits_own_suggested_only(client, library_sde, login_as):
    login_as(character_id=1, name="One", role="pilot")
    fit_id = post(client, "/api/fits", {"eft_text": ABSO_FIT}).json()["id"]
    assert patch(client, f"/api/fits/{fit_id}", {"name": "Renamed"}).status_code == 200
    assert patch(client, f"/api/fits/{fit_id}", {"status": "active"}).status_code == 403
    client.get("/auth/logout")
    login_as(character_id=2, name="Two", role="pilot")
    resp = patch(client, f"/api/fits/{fit_id}", {"name": "Hijack"})
    assert resp.status_code == 403
    assert client.get(f"/api/fits/{fit_id}").json()["can_edit"] is False


def test_theorycrafter_activates_with_audit(client, library_sde, login_as):
    login_as(character_id=1, name="One", role="pilot")
    fit_id = post(client, "/api/fits", {"eft_text": ABSO_FIT}).json()["id"]
    client.get("/auth/logout")
    login_as(character_id=3, name="Theo", role="theorycrafter")
    resp = patch(client, f"/api/fits/{fit_id}", {"status": "active", "reason": "looks good"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active" and body["reviewed_by_name"] == "Theo" and body["reviewed_at"]
    entry = AuditLog.objects.get(action="fit.status_changed")
    assert entry.reason == "looks good" and entry.after == {"status": "active"}
    assert AuditLog.objects.filter(action="fit.created").count() == 1
    # pilot can no longer edit an active fit
    client.get("/auth/logout")
    login_as(character_id=1, name="One", role="pilot")
    assert patch(client, f"/api/fits/{fit_id}", {"name": "x"}).status_code == 403


def test_list_filters(client, library_sde, login_as):
    login_as(role="theorycrafter")
    post(client, "/api/fits", {"eft_text": ABSO_FIT, "status": "active"})
    post(client, "/api/fits", {"eft_text": ABSO_FIT, "name": "Second", "status": "retired"})
    post(client, "/api/fits", {"eft_text": "[Rifter, Rifty]\nStasis Webifier II\n"})
    assert len(client.get("/api/fits").json()) == 3
    assert [f["name"] for f in client.get("/api/fits", {"status": "active"}).json()] == [
        "Octo Ewar Abso"
    ]
    assert len(client.get("/api/fits", {"status": "active,retired"}).json()) == 2
    assert [f["ship_name"] for f in client.get("/api/fits", {"q": "rift"}).json()] == ["Rifter"]
    assert len(client.get("/api/fits", {"ship": 22448}).json()) == 2
    summary = client.get("/api/fits").json()[0]
    assert "eft_text" not in summary and summary["unresolved_count"] == 0


def test_legality_endpoint(client, library_sde, imported_atxxii, login_as):
    login_as()
    fit_id = post(client, "/api/fits", {"eft_text": ABSO_FIT}).json()["id"]
    body = client.get(f"/api/fits/{fit_id}/legality", {"ruleset": "ATXXII"}).json()
    assert body["is_legal"] and body["ruleset"] == "ATXXII"
    assert [v["code"] for v in body["violations"]] == ["META_LEVEL_TOO_HIGH"]
    assert body["violations"][0]["line_nos"] == [9]
    assert client.get(f"/api/fits/{fit_id}/legality", {"ruleset": "NOPE"}).status_code == 404
    Fit.objects.filter(pk=fit_id).update(
        eft_text=ABSO_FIT.replace("Stasis Webifier II", "Federation Navy Stasis Webifier")
    )
    assert not client.get(f"/api/fits/{fit_id}/legality", {"ruleset": "ATXXII"}).json()["is_legal"]
    flag = client.get(f"/api/fits/{fit_id}/legality", {"ruleset": "ATXXII", "flagship": "true"})
    assert flag.json()["is_legal"] and flag.json()["is_flagship"]
