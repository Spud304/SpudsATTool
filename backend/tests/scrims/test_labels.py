import json

import pytest

from apps.audit.models import AuditLog
from apps.scrims import sets
from apps.scrims.models import WarpInLabel

pytestmark = pytest.mark.django_db
JSON = "application/json"


def test_warp_labels_crud_and_in_use_guard(client, scrim, captain, login_as):
    login_as(character_id=6, name="Viewer", role="viewer")
    listing = client.get("/api/warp-labels")
    assert listing.status_code == 200 and len(listing.json()) >= 40  # the sheet's seed
    assert (
        client.post("/api/warp-labels", json.dumps({"label": "x"}), content_type=JSON).status_code
        == 403
    )
    client.get("/auth/logout")

    login_as(character_id=1, name="Spud", role="admin")
    resp = client.post(
        "/api/warp-labels", json.dumps({"label": " Gate 0 ", "sort_order": 99}), content_type=JSON
    )
    assert resp.status_code == 201, resp.content
    row = resp.json()
    assert row["label"] == "Gate 0" and row["in_use"] == 0
    assert (
        client.post(
            "/api/warp-labels", json.dumps({"label": "Gate 0"}), content_type=JSON
        ).status_code
        == 409
    )
    resp = client.patch(
        f"/api/warp-labels/{row['id']}", json.dumps({"is_active": False}), content_type=JSON
    )
    assert resp.status_code == 200 and resp.json()["is_active"] is False
    assert "Gate 0" not in client.get("/api/scrims/vocab").json()["warp_labels"]

    # used by a set: cannot delete
    doc = sets.create_set(captain, scrim.pk)
    sets.patch_set(captain, scrim.pk, doc["id"], warp_calls=["Gate 0"])
    assert client.get("/api/warp-labels").json()[-1]["in_use"] == 1 or any(
        r["label"] == "Gate 0" and r["in_use"] == 1 for r in client.get("/api/warp-labels").json()
    )
    assert client.delete(f"/api/warp-labels/{row['id']}").status_code == 409
    sets.patch_set(captain, scrim.pk, doc["id"], warp_calls=[])
    assert client.delete(f"/api/warp-labels/{row['id']}").status_code == 204
    assert not WarpInLabel.objects.filter(label="Gate 0").exists()
    assert AuditLog.objects.filter(action__startswith="warp_label.").count() == 3
