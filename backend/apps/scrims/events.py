"""The session-level write lock and the append-only event log behind the live stream.

Every scrim mutation (sets, header, archive, RSVP, attendance) runs inside `locked(session_id)`,
which takes a row lock on the Session so concurrent editors serialise; `emit()` then bumps
`event_seq`, stores a `ChangeEvent` and publishes it to the broker once the transaction commits. Set events carry the whole set document (see
`derived.py`); header and attendance events carry nothing and tell clients to refetch.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import transaction
from django.db.models import F

from . import broker
from .models import ChangeEvent, Session

KIND_SET = "set"
KIND_SET_DELETED = "set_deleted"
KIND_SESSION = "session"
KIND_ATTENDANCE = "attendance"
KIND_PING = "ping"  # keepalive frame; EventSource cannot observe SSE comments
KIND_PRESENCE = "presence"  # not stored: no seq, published straight to the broker
KIND_RESYNC = "resync"  # emitted by the stream when replay would be too long


@contextmanager
def locked(session_id: int) -> Iterator[Session]:
    with transaction.atomic():
        yield Session.objects.select_for_update().get(pk=session_id)


def emit(session: Session, kind: str, payload: dict, actor=None) -> ChangeEvent:
    """Inside `locked()`: record the change and publish it after commit."""
    # Atomic increment: a caller may hold a stale copy of the row, so never write the in-memory value.
    Session.objects.filter(pk=session.pk).update(event_seq=F("event_seq") + 1)
    session.refresh_from_db(fields=["event_seq"])
    if kind == KIND_SET:
        # Stamped so a client can tell a late copy of this set (a slow reply) from a newer one.
        payload["set"]["seq"] = session.event_seq
    event = ChangeEvent.objects.create(
        session=session,
        seq=session.event_seq,
        kind=kind,
        payload=payload,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
    )
    # The stream replays at most 500 events; older ones are dead weight (each carries a set document).
    ChangeEvent.objects.filter(session=session, seq__lt=event.seq - 500).delete()
    message = as_message(event)
    # Robust: the write has committed, so a broker outage must not turn it into a 500 (and a
    # retried duplicate). Open pages catch up from the replay when they reconnect.
    transaction.on_commit(lambda: broker.get_broker().publish(session.pk, message), robust=True)
    return event


def notify(session_id: int, kind: str, actor=None, payload: dict | None = None) -> None:
    """For a caller not already holding the lock, such as the roster attaching a pilot to scrims."""
    with locked(session_id) as session:
        emit(session, kind, payload or {}, actor)


def as_message(event: ChangeEvent) -> dict:
    return {"seq": event.seq, "kind": event.kind, "payload": event.payload}


def publish_transient(session_id: int, kind: str, payload: dict) -> None:
    """Presence and other messages that need no replay: straight to the broker, no seq."""
    broker.get_broker().publish(session_id, {"seq": None, "kind": kind, "payload": payload})
