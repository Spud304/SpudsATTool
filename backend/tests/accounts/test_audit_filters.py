from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import record

pytestmark = pytest.mark.django_db


def test_filters_and_facets(client, team, admins, login_as):
    login_as(role=None)
    client.get("/auth/logout")
    login_as(character_id=2, name="Cap", role="captain")
    cap = client.get("/api/me").json()
    record(actor=None, action="pilot.created", target_label="Fryon", after={"merc": True})
    old = AuditLog.objects.create(
        actor_id=cap["user_id"], action="scrim.created", target_label="Old night", reason="long ago"
    )
    AuditLog.objects.filter(pk=old.pk).update(at=timezone.now() - timedelta(days=30))

    def ids(**params):
        return {e["id"] for e in client.get("/api/audit", params).json()["items"]}

    everything = ids()
    assert old.pk in everything
    assert ids(actor_id=cap["user_id"]) == {old.pk} | {
        e["id"]
        for e in client.get("/api/audit", {"actor_id": cap["user_id"]}).json()["items"]
        if e["id"] != old.pk
    }
    assert ids(action="pilot.") == ids(action="pilot.created") and ids(action="pilot.")
    assert ids(q="fryon") == ids(action="pilot.created")
    assert ids(q="long ago") == {old.pk}
    today = timezone.localdate().isoformat()
    assert old.pk not in ids(since=today)
    assert ids(until=(timezone.localdate() - timedelta(days=1)).isoformat()) == {old.pk}

    facets = client.get("/api/audit/facets").json()
    assert "pilot.created" in facets["actions"] and "scrim.created" in facets["actions"]
    assert {a["user_id"] for a in facets["actors"]} >= {
        cap["user_id"]
    }  # the env admin acted through no request
    assert facets["actors"] == sorted(facets["actors"], key=lambda a: a["display_name"])

    client.get("/auth/logout")
    login_as(character_id=3, name="Just A Pilot", role="pilot")
    assert client.get("/api/audit/facets").status_code == 403
