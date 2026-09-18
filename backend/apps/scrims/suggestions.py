"""Who has flown a hull before: the pilot dropdown lists them first, with a count and the last date."""

from django.core.cache import cache
from django.db.models import Count, Max

from .models import Assignment, LineupSide, Outcome

CACHE_SECONDS = 60


def pilot_history(type_id: int, exclude_session_id: int | None = None) -> list[dict]:
    key = f"scrims:pilot-history:{type_id}:{exclude_session_id or 0}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    qs = Assignment.objects.filter(
        side=LineupSide.US,
        ship_id=type_id,
        pilot__isnull=False,
        round__deleted_at__isnull=True,
        round__set__deleted_at__isnull=True,
        round__set__session__is_archived=False,
    ).exclude(round__outcome=Outcome.RESET)
    if exclude_session_id is not None:
        qs = qs.exclude(round__set__session_id=exclude_session_id)
    rows = (
        qs.values("pilot_id", "pilot__name")
        .annotate(flights=Count("id"), last_date=Max("round__set__session__date"))
        .order_by("-flights", "-last_date", "pilot__name")
    )
    out = [
        {
            "pilot_id": r["pilot_id"],
            "pilot_name": r["pilot__name"],
            "flights": r["flights"],
            "last_date": r["last_date"].isoformat() if r["last_date"] else None,
        }
        for r in rows
    ]
    cache.set(key, out, CACHE_SECONDS)
    return out
