import json

import pytest

from apps.accounts import roles
from apps.library.models import Fit
from tests.conftest import ABSO_FIT
from tests.rules.engine import atxxii as at

RATTLESNAKE = 17918
pytestmark = pytest.mark.django_db
JSON = "application/json"


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type=JSON)


def patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type=JSON)


def slots(*type_ids, overrides=None):
    overrides = overrides or {}
    return [
        {"slot_no": i, "type_id": t, **overrides.get(i, {})}
        for i, t in enumerate(type_ids, start=1)
    ]


def test_auth_matrix(client, library_sde, imported_atxxii, login_as):
    assert client.get("/api/comps").status_code == 401
    login_as(role="viewer")
    assert client.get("/api/comps").status_code == 403
    client.get("/auth/logout")
    login_as(role="pilot")
    assert client.get("/api/comps").status_code == 200
    assert client.get("/api/comps/vocab").status_code == 200
    pilot_role = roles.by_slug("pilot")
    pilot_role.permissions = [p for p in pilot_role.permissions if p != "browse_library"]
    pilot_role.save()
    assert client.get("/api/comps").status_code == 403


def test_create_list_filters_and_bans(client, library_sde, imported_atxxii, login_as):
    login_as(character_id=3, name="Theo", role="theorycrafter")
    resp = post(client, "/api/comps", {"name": "OF99", "status": "active"})
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["ruleset"] == "ATXXII" and body["fielded_pilots"] == 10 and len(body["slots"]) == 10
    assert body["evaluation"]["total_points"] == 0 and body["can_edit"]
    comp_id = body["id"]
    resp = patch(client, f"/api/comps/{comp_id}", {"slots": slots(*at.OF99_SET1)})
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["evaluation"]["total_points"] == 200 and body["evaluation"]["is_legal"]
    assert body["evaluation_detail"]["cap_status"] == "EXACT"
    assert body["hulls"][0] == "Astarte"

    vocab = client.get("/api/comps/vocab").json()
    rush = next(a for a in vocab["archetypes"] if a["name"] == "Rush")
    post(
        client,
        "/api/comps",
        {"name": "Snakes", "status": "construction", "archetype_id": rush["id"]},
    )
    snakes = client.get("/api/comps", {"q": "snakes"}).json()[0]
    patch(client, f"/api/comps/{snakes['id']}", {"slots": slots(RATTLESNAKE, *at.OF99_SET1[1:])})

    assert len(client.get("/api/comps").json()) == 2
    assert [c["name"] for c in client.get("/api/comps", {"status": "active"}).json()] == ["OF99"]
    assert [c["name"] for c in client.get("/api/comps", {"archetype": rush["id"]}).json()] == [
        "Snakes"
    ]
    assert [c["name"] for c in client.get("/api/comps", {"q": "rattle"}).json()] == ["Snakes"]
    assert client.get("/api/comps", {"ruleset": "NOPE"}).json() == []

    banned = client.get("/api/comps", {"banned": str(RATTLESNAKE)}).json()
    by_name = {c["name"]: c for c in banned}
    assert by_name["Snakes"]["evaluation"]["banned_hulls"] == ["Rattlesnake"]
    assert not by_name["Snakes"]["evaluation"]["is_legal"]
    assert (
        by_name["OF99"]["evaluation"]["banned_hulls"] == []
        and by_name["OF99"]["evaluation"]["is_legal"]
    )
    assert client.get("/api/comps", {"banned": "x,1"}).status_code == 422


def test_pilot_flow_and_can_edit(client, library_sde, imported_atxxii, login_as):
    login_as(character_id=1, name="One", role="pilot")
    resp = post(client, "/api/comps", {"name": "Idea", "status": "active"})
    assert resp.status_code == 403
    comp = post(client, "/api/comps", {"name": "Idea"}).json()
    assert comp["status"] == "suggested" and comp["can_edit"]
    assert patch(client, f"/api/comps/{comp['id']}", {"notes": "try it"}).status_code == 200
    assert patch(client, f"/api/comps/{comp['id']}", {"status": "active"}).status_code == 403
    client.get("/auth/logout")

    login_as(character_id=2, name="Two", role="pilot")
    assert patch(client, f"/api/comps/{comp['id']}", {"notes": "mine now"}).status_code == 403
    assert client.get(f"/api/comps/{comp['id']}").json()["can_edit"] is False
    client.get("/auth/logout")

    login_as(character_id=3, name="Theo", role="theorycrafter")
    resp = patch(
        client, f"/api/comps/{comp['id']}", {"status": "construction", "reason": "promising"}
    )
    assert resp.status_code == 200 and resp.json()["reviewed_by_name"] == "Theo"
    client.get("/auth/logout")
    login_as(character_id=1, name="One", role="pilot")
    assert patch(client, f"/api/comps/{comp['id']}", {"notes": "x"}).status_code == 403


def test_vocab_archetypes_and_clone(client, library_sde, imported_atxxii, login_as):
    login_as(character_id=1, name="One", role="pilot")
    vocab = client.get("/api/comps/vocab").json()
    assert len(vocab["link_scripts"]) == 12 and len(vocab["archetypes"]) == 16
    assert sum(a["is_retired"] for a in vocab["archetypes"]) == 2
    assert vocab["statuses"] == ["suggested", "construction", "active", "inactive", "retired"]
    assert vocab["active_ruleset"] == "ATXXII"
    assert post(client, "/api/comps/archetypes", {"name": "Bait"}).status_code == 403
    client.get("/auth/logout")

    login_as(character_id=3, name="Theo", role="theorycrafter")
    resp = post(client, "/api/comps/archetypes", {"name": "Bait"})
    assert resp.status_code == 201
    resp = patch(client, f"/api/comps/archetypes/{resp.json()['id']}", {"is_retired": True})
    assert resp.status_code == 200 and resp.json()["is_retired"]

    fit_id = post(client, "/api/fits", {"eft_text": ABSO_FIT, "status": "active"}).json()["id"]
    comp = post(client, "/api/comps", {"name": "Source", "status": "active"}).json()
    body = patch(
        client,
        f"/api/comps/{comp['id']}",
        {
            "slots": slots(
                *at.OF99_SET1,
                overrides={3: {"default_fit_id": fit_id, "link_scripts": ["AE", "AR"]}},
            )
        },
    ).json()
    slot3 = body["slots"][2]
    assert slot3["default_fit_name"] == "Octo Ewar Abso" and slot3["default_fit_has_links"]
    assert body["evaluation_detail"]["slots"][2]["link_index"] == 1
    assert body["stats"]["fits_set"] == 1

    resp = post(client, f"/api/comps/{comp['id']}/clone", {"name": "Copy"})
    assert resp.status_code == 201 and resp.json()["slots"][2]["default_fit_id"] == fit_id

    Fit.objects.filter(pk=fit_id).update(status="inactive")
    assert (
        client.get(f"/api/comps/{comp['id']}").json()["slots"][2]["default_fit_status"]
        == "inactive"
    )


def test_slots_past_a_reduced_pilot_count_are_flagged_and_clearable(
    client, library_sde, imported_atxxii, login_as
):
    ruleset, _ = imported_atxxii
    login_as(role="theorycrafter")
    comp = post(client, "/api/comps", {"name": "Big"}).json()
    lineup = [at.RIFTER] * 8 + [RATTLESNAKE, at.RIFTER]
    assert patch(client, f"/api/comps/{comp['id']}", {"slots": slots(*lineup)}).status_code == 200
    ruleset.fielded_pilots = 8  # a re-imported rules revision
    ruleset.save()

    body = client.get(f"/api/comps/{comp['id']}").json()
    assert [s["slot_no"] for s in body["slots"] if s["over_count"]] == [9, 10]
    codes = [v["code"] for v in body["evaluation_detail"]["violations"]]
    assert "SLOTS_OVER_COUNT" in codes and "WRONG_SLOT_COUNT" not in codes
    # the editor still saves slots 1..8 while 9 and 10 wait to be cleared
    resp = patch(client, f"/api/comps/{comp['id']}", {"slots": slots(*lineup[:8])})
    assert resp.status_code == 200, resp.content
    body = patch(client, f"/api/comps/{comp['id']}", {"clear_over_count": True}).json()
    assert [s["slot_no"] for s in body["slots"]] == list(range(1, 9))
    assert "SLOTS_OVER_COUNT" not in [v["code"] for v in body["evaluation_detail"]["violations"]]


def test_create_with_a_lineup_is_all_or_nothing(client, library_sde, imported_atxxii, login_as):
    from apps.library.models import Comp

    login_as(role="theorycrafter")
    bad = slots(*([at.RIFTER] * 9 + [424242]))  # slot 10: no such hull
    assert post(client, "/api/comps", {"name": "From pad", "slots": bad}).status_code == 422
    assert not Comp.objects.filter(name="From pad").exists()
    body = post(client, "/api/comps", {"name": "From pad", "slots": slots(*[at.RIFTER] * 10)})
    assert body.status_code == 201
    assert [s["type_id"] for s in body.json()["slots"]] == [at.RIFTER] * 10


def test_archetype_patch_ignores_nulls_and_refuses_blank(
    client, library_sde, imported_atxxii, login_as
):
    login_as(role="theorycrafter")
    arch = post(client, "/api/comps/archetypes", {"name": "Brawl"}).json()
    url = f"/api/comps/archetypes/{arch['id']}"
    resp = patch(client, url, {"name": None, "description": None, "is_retired": None})
    assert resp.status_code == 200 and resp.json()["name"] == "Brawl"
    assert patch(client, url, {"name": "  "}).status_code == 422
