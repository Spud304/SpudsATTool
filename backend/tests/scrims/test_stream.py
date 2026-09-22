import asyncio
import json
from typing import Any, cast

import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient

from apps.scrims import broker, events, presence, sets
from apps.scrims.broker import MemoryBroker
from apps.scrims.models import ChangeEvent
from apps.scrims.stream import event_stream, format_event


def parse(frame: str) -> dict:
    data = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data[len("data: ") :])


def test_format_event_carries_the_seq_as_id():
    frame = format_event({"seq": 7, "kind": "set", "payload": {"set": {"id": 1}}})
    assert frame.startswith("id: 7\nevent: set\ndata: ") and frame.endswith("\n\n")
    assert "id:" not in format_event({"seq": None, "kind": "presence", "payload": {}})


async def test_memory_broker_delivers_to_every_subscriber():
    broker.reset_broker()
    b = cast(MemoryBroker, broker.get_broker())
    one, two = b.subscribe(1), b.subscribe(1)
    await one.open()
    await two.open()
    other = b.subscribe(2)
    await other.open()
    b.publish(1, {"seq": 1, "kind": "set", "payload": {}})
    got_one, got_two = await one.get(1), await two.get(1)
    assert got_one and got_two and got_one["seq"] == 1 and got_two["seq"] == 1
    assert await other.get(0.05) is None
    await one.close()
    assert b.subscriber_count(1) == 1


@pytest.mark.django_db(transaction=True)
async def test_stream_replays_then_relays_and_flags_gaps(scrim, captain):
    session_id = scrim.pk
    await sync_to_async(events.notify)(session_id, events.KIND_SESSION, captain)
    await sync_to_async(events.notify)(session_id, events.KIND_ATTENDANCE, captain)

    stream = event_stream(session_id, 0, keepalive=0.2)
    first, second, third = [await anext(stream) for _ in range(3)]
    assert first.startswith("id: 1\nevent: session") and second.startswith(
        "id: 2\nevent: attendance"
    )
    assert parse(third)["kind"] == "presence" and parse(third)["payload"]["viewers"] == []

    assert parse(await anext(stream))["kind"] == "ping"  # idle keepalive

    # A live write lands as the next frame with its seq.
    await sync_to_async(events.notify)(session_id, events.KIND_SESSION, captain)
    frame = await asyncio.wait_for(anext(stream), 2)
    assert frame.startswith("id: 3\nevent: session")

    # Stale and out-of-order messages: an old seq is dropped, a jump is flagged for a refetch.
    b = broker.get_broker()
    b.publish(session_id, {"seq": 2, "kind": "session", "payload": {}})
    b.publish(session_id, {"seq": 6, "kind": "set", "payload": {"set": {"id": 9}}})
    frame = await asyncio.wait_for(anext(stream), 2)
    assert parse(frame)["kind"] == "resync"
    frame = await asyncio.wait_for(anext(stream), 2)
    assert frame.startswith("id: 6\nevent: set")
    await stream.aclose()


@pytest.mark.django_db(transaction=True)
async def test_stream_resumes_from_last_event_id_and_caps_replay(scrim, captain):
    session_id = scrim.pk
    for _ in range(3):
        await sync_to_async(events.notify)(session_id, events.KIND_SESSION, captain)
    stream = event_stream(session_id, 2, keepalive=0.2)
    frame = await anext(stream)
    assert frame.startswith("id: 3\n")
    await stream.aclose()

    # More than REPLAY_CAP events since the client's seq: one resync frame instead of a flood.
    from apps.scrims import stream as stream_mod

    stream_mod.REPLAY_CAP = 1
    try:
        stream = event_stream(session_id, 0, keepalive=0.2)
        frame = await anext(stream)
        assert parse(frame)["kind"] == "resync" and parse(frame)["seq"] == 3
        await stream.aclose()
    finally:
        stream_mod.REPLAY_CAP = 500


@pytest.mark.django_db(transaction=True)
async def test_events_view_needs_a_member(scrim, client, login_as):
    aclient = AsyncClient()
    resp = await aclient.get(f"/api/scrims/{scrim.pk}/events")
    assert resp.status_code == 401
    resp = await aclient.get("/api/scrims/999999/events")
    assert resp.status_code == 404

    # login_as drives the sync test client; the async client borrows its session cookie.
    await sync_to_async(login_as)(character_id=9, name="Guest", role="guest")
    aclient.cookies = client.cookies
    resp = await aclient.get(f"/api/scrims/{scrim.pk}/events")
    assert resp.status_code == 403

    await sync_to_async(login_as)(character_id=10, name="Member", role="pilot")
    aclient.cookies = client.cookies
    await sync_to_async(scrim.refresh_from_db)()  # the two logins joined the roll call: events
    resp = cast(
        Any,
        await aclient.get(
            f"/api/scrims/{scrim.pk}/events", headers={"Last-Event-ID": str(scrim.event_seq)}
        ),
    )
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/event-stream")
    assert resp["X-Accel-Buffering"] == "no"
    first = await anext(aiter(resp.streaming_content))
    assert parse(first.decode())["kind"] == "presence"  # nothing to replay yet
    await resp.streaming_content.aclose()


def test_presence_heartbeat_snapshot_and_leave(db, scrim, captain, pilot):
    assert presence.snapshot(scrim.pk) == []
    viewers = presence.heartbeat(scrim.pk, captain, "us.3.fit")
    assert [v["name"] for v in viewers] == ["Cap"] and viewers[0]["focus"] == "us.3.fit"
    viewers = presence.heartbeat(scrim.pk, pilot, None)
    assert [v["name"] for v in viewers] == ["Cap", "Pilot One"]
    published = cast(MemoryBroker, broker.get_broker()).published
    assert published[-1][1]["kind"] == "presence" and published[-1][1]["seq"] is None
    assert [v["name"] for v in presence.leave(scrim.pk, captain)] == ["Pilot One"]
    assert not ChangeEvent.objects.filter(kind="presence").exists()  # transient, never stored


def test_part_a_writes_announce_themselves(db, scrim, captain, pilot):
    from apps.scrims import sessions

    sessions.set_rsvp(pilot, scrim, "yes")
    sessions.update_session(captain, scrim, title="OF 99 v2")
    kinds = list(
        ChangeEvent.objects.filter(session=scrim).order_by("seq").values_list("kind", flat=True)
    )
    assert kinds == ["attendance", "session"]
    doc = sets.create_set(captain, scrim.pk)
    assert ChangeEvent.objects.get(seq=3).payload["set"]["id"] == doc["id"]


@pytest.mark.django_db(transaction=True)
async def test_stream_ends_when_access_is_withdrawn(scrim, captain):
    calls = 0

    async def allowed() -> bool:
        nonlocal calls
        calls += 1
        return calls < 2

    stream = event_stream(scrim.pk, 0, keepalive=0.1, allowed=allowed)
    frames = []
    with pytest.raises(StopAsyncIteration):
        for _ in range(10):
            frames.append(await asyncio.wait_for(anext(stream), 2))
    assert calls == 2 and [parse(f)["kind"] for f in frames] == ["presence", "ping"]


@pytest.mark.django_db(transaction=True)
async def test_member_access_is_read_fresh(scrim, captain, viewer):
    from apps.accounts import roles
    from apps.scrims.stream import _member_can_view

    assert await sync_to_async(_member_can_view)(viewer.pk, scrim.pk)
    membership = await sync_to_async(lambda: viewer.membership)()
    membership.role = await sync_to_async(roles.by_slug)("guest")
    await sync_to_async(membership.save)()
    assert not await sync_to_async(_member_can_view)(viewer.pk, scrim.pk)


@pytest.mark.django_db
def test_replay_resumes_from_the_last_row_read(scrim, captain):
    from apps.scrims.stream import _replay

    for _ in range(3):
        events.notify(scrim.pk, events.KIND_SESSION, captain)
    # Event 3 committing between the replay's two queries looks like this: not in the rows,
    # already counted in event_seq. It arrives on the subscription and must not be skipped.
    ChangeEvent.objects.filter(session=scrim, seq=3).delete()
    replayed, last = _replay(scrim.pk, 0)
    assert [m["seq"] for m in replayed] == [1, 2] and last == 2
    assert _replay(scrim.pk, 5) == ([], 3)  # a client ahead of the server resumes at the server


@pytest.mark.django_db
def test_a_broker_outage_does_not_fail_a_committed_write(
    scrim, captain, monkeypatch, django_capture_on_commit_callbacks
):
    class Down:
        def publish(self, session_id, message):
            raise ConnectionError("redis is down")

    monkeypatch.setattr(broker, "get_broker", lambda: Down())
    with django_capture_on_commit_callbacks(execute=True):
        doc = sets.create_set(captain, scrim.pk)
    assert doc["seq"] == ChangeEvent.objects.get(session=scrim).seq
