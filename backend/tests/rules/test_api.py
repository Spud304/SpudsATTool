import pytest

from .engine import atxxii as at

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug(settings):
    settings.DEBUG = True


def test_endpoints_closed_outside_debug(client, imported_atxxii):
    assert client.get("/api/rulesets").status_code == 401
    assert client.get("/api/rulesets/ATXXII/ships").status_code == 401


def test_list_rulesets(client, imported_atxxii, debug):
    body = client.get("/api/rulesets").json()
    assert [r["code"] for r in body] == ["ATXXII"]
    rs = body[0]
    assert rs["point_cap"] == 200 and rs["fielded_pilots"] == 10 and rs["has_point_table"]
    assert {h["size"]: h["duplicate_surcharge"] for h in rs["hull_sizes"]}["BC"] == 3


def test_list_ships(client, imported_atxxii, debug):
    ships = client.get("/api/rulesets/ATXXII/ships").json()
    by_name = {s["name"]: s for s in ships}
    assert by_name["Astarte"]["points"] == 33 and by_name["Astarte"]["hull_size"] == "BC"
    assert by_name["Bhaalgorn"]["flagship_eligible"] is False
    assert by_name["Rattlesnake"]["is_unique"] is True
    assert [s["name"] for s in ships] == sorted(s["name"] for s in ships)
    assert client.get("/api/rulesets/NOPE/ships").status_code == 404


def test_evaluate_of99(client, imported_atxxii, debug):
    payload = {
        "slots": [{"slot_no": i, "type_id": t} for i, t in enumerate(at.OF99_SET1, start=1)],
        "bans": [],
    }
    resp = client.post("/api/rulesets/ATXXII/evaluate", payload, content_type="application/json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["total_points"] == 200 and body["is_legal"] and body["cap_status"] == "EXACT"
    assert [s["total_points"] for s in body["slots"][:2]] == [36, 36]


def test_evaluate_with_ban_and_flagship(client, imported_atxxii, debug):
    payload = {
        "slots": [
            {"slot_no": 1, "type_id": at.RATTLESNAKE, "is_flagship": True},
            {"slot_no": 2, "type_id": at.RATTLESNAKE},
        ],
        "bans": [{"type_id": at.RATTLESNAKE, "made_by_side": "B"}],
    }
    body = client.post(
        "/api/rulesets/ATXXII/evaluate", payload, content_type="application/json"
    ).json()
    codes = {v["code"] for v in body["violations"]}
    assert "BANNED" in codes and "WRONG_SLOT_COUNT" in codes
    assert body["slots"][0]["is_banned"] is False and body["slots"][1]["is_banned"] is True
    banned = next(v for v in body["violations"] if v["code"] == "BANNED")
    assert banned["slot_nos"] == [2]
