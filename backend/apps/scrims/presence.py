"""Who has a scrim page open. Viewers POST a heartbeat every 15 s; entries live 45 s in the cache."""

from django.core.cache import cache
from django.utils import timezone

from . import events

TTL_SECONDS = 45


def _entry_key(session_id: int, user_id: int) -> str:
    return f"scrim:{session_id}:presence:{user_id}"


def _ids_key(session_id: int) -> str:
    return f"scrim:{session_id}:presence-ids"


def snapshot(session_id: int) -> list[dict]:
    ids = cache.get(_ids_key(session_id)) or []
    entries = cache.get_many([_entry_key(session_id, uid) for uid in ids])
    alive = [uid for uid in ids if _entry_key(session_id, uid) in entries]
    if alive != ids:
        cache.set(_ids_key(session_id), alive, 3600)
    return sorted(entries.values(), key=lambda e: e["name"].lower())


def heartbeat(session_id: int, user, focus: str | None) -> list[dict]:
    entry = {
        "user_id": user.pk,
        "name": user.display_name,
        "focus": focus or None,
        "at": timezone.now().isoformat(),
    }
    cache.set(_entry_key(session_id, user.pk), entry, TTL_SECONDS)
    ids = list(cache.get(_ids_key(session_id)) or [])
    if user.pk not in ids:
        ids.append(user.pk)
        cache.set(_ids_key(session_id), ids, 3600)
    viewers = snapshot(session_id)
    events.publish_transient(session_id, events.KIND_PRESENCE, {"viewers": viewers})
    return viewers


def leave(session_id: int, user) -> list[dict]:
    cache.delete(_entry_key(session_id, user.pk))
    viewers = snapshot(session_id)
    events.publish_transient(session_id, events.KIND_PRESENCE, {"viewers": viewers})
    return viewers
