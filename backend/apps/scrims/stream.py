"""`GET /api/scrims/<id>/events`: the server-sent-events stream behind the live scrim page.

Replays stored events after the client's `Last-Event-ID`, then relays broker messages; a comment
`ping` event every `keepalive` seconds keeps proxies from closing the idle connection.
"""

import json
from collections.abc import AsyncGenerator

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from ninja.errors import HttpError

from apps.accounts import permissions

from . import broker, events, presence
from .models import ChangeEvent, Session

REPLAY_CAP: int = 500
KEEPALIVE_SECONDS = 20.0


def format_event(message: dict) -> str:
    """One SSE frame. Stored events carry their seq as the id so the browser resumes from it."""
    lines = []
    if message.get("seq") is not None:
        lines.append(f"id: {message['seq']}")
    lines.append(f"event: {message['kind']}")
    lines.append(f"data: {json.dumps(message, separators=(',', ':'))}")
    return "\n".join(lines) + "\n\n"


def _replay(session_id: int, since: int) -> tuple[list[dict], int]:
    rows = list(
        ChangeEvent.objects.filter(session_id=session_id, seq__gt=since).order_by("seq")[
            : REPLAY_CAP + 1
        ]
    )
    current = Session.objects.filter(pk=session_id).values_list("event_seq", flat=True).first() or 0
    if len(rows) > REPLAY_CAP:
        return [
            {
                "seq": current,
                "kind": events.KIND_RESYNC,
                "payload": {"reason": "too many events since last seen"},
            }
        ], current
    return [events.as_message(e) for e in rows], current


async def event_stream(
    session_id: int, since: int, *, keepalive: float = KEEPALIVE_SECONDS
) -> AsyncGenerator[str, None]:
    sub = broker.get_broker().subscribe(session_id)
    await sub.open()  # subscribe first, replay second: nothing slips between the two
    try:
        replayed, last_seq = await sync_to_async(_replay)(session_id, since)
        for message in replayed:
            yield format_event(message)
        viewers = await sync_to_async(presence.snapshot)(session_id)
        yield format_event(
            {"seq": None, "kind": events.KIND_PRESENCE, "payload": {"viewers": viewers}}
        )
        while True:
            message = await sub.get(keepalive)
            if message is None:
                yield format_event({"seq": None, "kind": events.KIND_PING, "payload": {}})
                continue
            seq = message.get("seq")
            if seq is not None:
                if seq <= last_seq:
                    continue  # already replayed
                if seq > last_seq + 1:
                    yield format_event(
                        {"seq": seq, "kind": events.KIND_RESYNC, "payload": {"reason": "gap"}}
                    )
                last_seq = seq
            yield format_event(message)
    finally:
        await sub.close()


def _since(request: HttpRequest) -> int:
    raw = request.headers.get("Last-Event-ID") or request.GET.get("since") or "0"
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


async def events_view(request: HttpRequest, session_id: int) -> HttpResponseBase:
    user = await request.auser()
    try:
        session = await Session.objects.filter(pk=session_id).afirst()
        if session is None:
            return JsonResponse({"detail": "not found"}, status=404)
        await sync_to_async(permissions.require_view_session)(user, session)
    except HttpError as exc:
        return JsonResponse({"detail": str(exc)}, status=exc.status_code)
    response = StreamingHttpResponse(
        event_stream(session_id, _since(request)), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
