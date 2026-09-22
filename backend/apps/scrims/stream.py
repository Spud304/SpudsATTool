"""`GET /api/scrims/<id>/events`: the server-sent-events stream behind the live scrim page.

Replays stored events after the client's `Last-Event-ID`, then relays broker messages; a `ping`
event every `keepalive` seconds keeps proxies from closing the idle connection.
"""

import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import cast

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.accounts.models import User

from . import broker, events, presence, share
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
    session_id: int,
    since: int,
    *,
    keepalive: float = KEEPALIVE_SECONDS,
    public: bool = False,
    allowed: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[str, None]:
    """`public` is a share-link viewer: set documents lose their fit text and presence is not sent.

    `allowed` is asked again every `keepalive` seconds; the stream ends when access is gone
    (link revoked, role changed), and the browser's reconnect then gets the 403 or 404.
    """
    scrub = share.strip_fit_text_from_message if public else (lambda m: m)
    sub = broker.get_broker().subscribe(session_id)
    await sub.open()  # subscribe first, replay second: nothing slips between the two
    try:
        replayed, last_seq = await sync_to_async(_replay)(session_id, since)
        for message in replayed:
            yield format_event(scrub(message))
        if not public:
            viewers = await sync_to_async(presence.snapshot)(session_id)
            yield format_event(
                {"seq": None, "kind": events.KIND_PRESENCE, "payload": {"viewers": viewers}}
            )
        next_check = time.monotonic() + keepalive
        while True:
            message = await sub.get(keepalive)
            if allowed is not None and time.monotonic() >= next_check:
                if not await allowed():
                    return
                next_check = time.monotonic() + keepalive
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
            if public and message.get("kind") == events.KIND_PRESENCE:
                continue
            yield format_event(scrub(message))
    finally:
        await sub.close()


def _member_can_view(user_id: int, session_id: int) -> bool:
    # Fresh rows: the request's user caches its membership and permission set.
    user = User.objects.filter(pk=user_id, is_active=True).first()
    session = Session.objects.filter(pk=session_id).first()
    return user is not None and session is not None and permissions.can_view_session(user, session)


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
    user_id = cast(int, user.pk)  # authenticated: require_view_session passed

    async def allowed() -> bool:
        return await sync_to_async(_member_can_view)(user_id, session_id)

    response = StreamingHttpResponse(
        event_stream(session_id, _since(request), allowed=allowed),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


async def share_events_view(request: HttpRequest, token: str) -> HttpResponseBase:
    session = await sync_to_async(share.resolve)(token)
    if session is None:
        return JsonResponse({"detail": "this share link is not valid"}, status=404)
    session_id = session.pk

    async def allowed() -> bool:
        current = await sync_to_async(share.resolve)(token)
        return current is not None and current.pk == session_id

    response = StreamingHttpResponse(
        event_stream(session_id, _since(request), public=True, allowed=allowed),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
