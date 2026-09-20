import json

import pytest

from apps.library import comps
from apps.library.models import Archetype

pytestmark = pytest.mark.django_db
JSON = "application/json"


def test_archetype_delete_refuses_when_used(client, library_sde, imported_atxxii, login_as):
    login_as(character_id=4, name="Theo", role="theorycrafter")
    resp = client.post("/api/comps/archetypes", json.dumps({"name": "Test Wedge"}), content_type=JSON)
    assert resp.status_code == 201
    kite = resp.json()
    assert kite["in_use"] == 0
    vocab = client.get("/api/comps/vocab").json()
    assert any(a["name"] == "Test Wedge" for a in vocab["archetypes"])

    comp = client.post(
        "/api/comps",
        json.dumps({"name": "Kitey", "archetype_id": kite["id"], "notes": "", "ban_theory": ""}),
        content_type=JSON,
    )
    assert comp.status_code == 201
    assert client.delete(f"/api/comps/archetypes/{kite['id']}").status_code == 409
    assert comps.archetype_uses(Archetype.objects.get(pk=kite["id"])) == 1
    client.patch(
        f"/api/comps/{comp.json()['id']}",
        json.dumps({"archetype_id": None, "reason": "x"}),
        content_type=JSON,
    )
    assert client.delete(f"/api/comps/archetypes/{kite['id']}").status_code == 204
    assert not Archetype.objects.filter(name="Test Wedge").exists()

    client.get("/auth/logout")
    login_as(character_id=5, name="Pilot", role="pilot")
    assert client.delete("/api/comps/archetypes/1").status_code == 403
