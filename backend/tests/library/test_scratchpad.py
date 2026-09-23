import json

import pytest

from apps.library.models import Scratchpad
from tests.rules.engine import atxxii as at

pytestmark = pytest.mark.django_db
JSON = "application/json"


def put(client, body):
    return client.put("/api/scratchpad", json.dumps(body), content_type=JSON)


def test_empty_document_names_the_active_ruleset(client, imported_atxxii, login_as):
    assert client.get("/api/scratchpad").status_code == 401
    login_as(role="pilot")
    doc = client.get("/api/scratchpad").json()
    assert doc == {"ruleset": "ATXXII", "slots": [], "bans": [], "updated_at": None}


def test_put_then_get_round_trips_per_user(client, imported_atxxii, login_as):
    login_as(character_id=11, name="One", role="pilot")
    body = {
        "ruleset": "ATXXII",
        "slots": [
            {"type_id": at.ASTARTE, "is_flagship": False, "has_links": True},
            {"type_id": None},
        ],
        "bans": [at.KERES],
    }
    resp = put(client, body)
    assert resp.status_code == 200, resp.content
    saved = resp.json()
    assert saved["ruleset"] == "ATXXII" and saved["bans"] == [at.KERES]
    assert saved["slots"][0] == {"type_id": at.ASTARTE, "is_flagship": False, "has_links": True}
    assert saved["slots"][1] == {"type_id": None, "is_flagship": False, "has_links": False}
    assert saved["updated_at"] is not None
    assert client.get("/api/scratchpad").json()["slots"] == saved["slots"]

    # A second save replaces, not appends; the row stays one per user.
    put(client, {"ruleset": None, "slots": [], "bans": []})
    assert client.get("/api/scratchpad").json() == {
        "ruleset": None,
        "slots": [],
        "bans": [],
        "updated_at": client.get("/api/scratchpad").json()["updated_at"],
    }
    assert Scratchpad.objects.count() == 1

    # Another member has their own, empty document.
    client.post("/auth/logout")
    login_as(character_id=12, name="Two", role="theorycrafter")
    assert client.get("/api/scratchpad").json()["slots"] == []


def test_guests_and_viewers_are_refused(client, imported_atxxii, login_as):
    login_as(character_id=13, name="Guest", role="guest")
    assert client.get("/api/scratchpad").status_code == 403
    assert put(client, {"slots": []}).status_code == 403
