import json
from datetime import timedelta
from typing import Any, cast

import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.scrims import sets, share
from apps.scrims.roster import ScrimError
from apps.scrims.stream import event_stream

pytestmark = pytest.mark.django_db


def test_create_resolve_and_revoke(scrim, captain):
    link = share.create_share(captain, scrim, days=3)
    assert len(link.token) >= 32 and share.is_live(link)
    assert share.resolve(link.token) == scrim
    assert AuditLog.objects.filter(
        action="share.created", scope=f"scrims.session:{scrim.pk}"
    ).exists()
    with pytest.raises(ScrimError):
        share.create_share(captain, scrim, days=0)

    link.expires_at = timezone.now() - timedelta(minutes=1)
    link.save()
    assert share.resolve(link.token) is None
    link.expires_at = timezone.now() + timedelta(days=1)
    link.save()
    share.revoke_share(captain, link)
    assert share.resolve(link.token) is None
    assert AuditLog.objects.filter(action="share.revoked").count() == 1
    share.revoke_share(captain, link)  # idempotent
    assert AuditLog.objects.filter(action="share.revoked").count() == 1
    assert share.resolve("nope") is None


def test_public_view_hides_fit_text_and_permissions(
    client, scrim, captain, theo, of99_comp, abso_fit
):
    doc = sets.create_set(captain, scrim.pk)
    sets.patch_set(theo, scrim.pk, doc["id"], comp_id=of99_comp.pk)
    link = share.create_share(captain, scrim)

    resp = client.get(f"/api/share/{link.token}")  # no login at all
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "OF 99" and body["can_manage"] is False and body["can_rsvp"] is False
    assert body["my_rsvp"] is None and all(a["is_me"] is False for a in body["attendance"])
    slot = body["sets"][0]["rounds"][0]["us"]["slots"][2]
    assert slot["fit_name"] == abso_fit.name and slot["fit_text"] == ""
    assert client.get("/api/share/not-a-token").status_code == 404

    scrim.is_archived = True
    scrim.save(update_fields=["is_archived"])
    assert client.get(f"/api/share/{link.token}").status_code == 404


def test_captain_endpoints_and_permissions(client, scrim, login_as):
    base = f"/api/scrims/{scrim.pk}/share"
    login_as(character_id=6, name="Viewer", role="viewer")
    assert client.post(base, json.dumps({}), content_type="application/json").status_code == 403
    assert client.get(base).status_code == 403
    client.post("/auth/logout")

    login_as(character_id=7, name="Cap", role="captain")
    resp = client.post(base, json.dumps({"days": 2}), content_type="application/json")
    assert resp.status_code == 201, resp.content
    link = resp.json()
    assert link["is_live"] and link["url"].endswith(f"/share/{link['token']}")
    assert client.get(base).json()[0]["id"] == link["id"]
    resp = client.delete(f"{base}/{link['id']}")
    assert resp.status_code == 200 and resp.json()["is_live"] is False
    assert client.get(f"/api/share/{link['token']}").status_code == 404
    assert (
        client.post(base, json.dumps({"days": 400}), content_type="application/json").status_code
        == 422
    )


@pytest.mark.django_db(transaction=True)
async def test_share_stream_needs_a_live_token_and_strips_fits(scrim, captain, theo, of99_comp):
    link = await sync_to_async(share.create_share)(captain, scrim)
    aclient = AsyncClient()
    assert (await aclient.get("/api/share/bogus/events")).status_code == 404
    resp = cast(Any, await aclient.get(f"/api/share/{link.token}/events"))
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/event-stream")
    await resp.streaming_content.aclose()

    await sync_to_async(scrim.refresh_from_db)()
    stream = event_stream(scrim.pk, scrim.event_seq, keepalive=0.2, public=True)
    first = await anext(stream)
    assert (
        '"kind":"ping"' in first
    )  # nothing after the fetched document, no presence for the public
    doc = await sync_to_async(sets.create_set)(captain, scrim.pk)
    await sync_to_async(sets.patch_set)(theo, scrim.pk, doc["id"], comp_id=of99_comp.pk)
    frames = [await anext(stream), await anext(stream)]
    payloads = [json.loads(f.split("data: ", 1)[1]) for f in frames]
    slots = payloads[-1]["payload"]["set"]["rounds"][0]["us"]["slots"]
    assert slots[2]["fit_name"] and all(s["fit_text"] == "" for s in slots)
    await stream.aclose()
