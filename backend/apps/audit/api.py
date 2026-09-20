from datetime import date, datetime
from typing import Any

from django.db.models import Q
from django.http import HttpRequest
from ninja import Query, Router, Schema
from ninja.pagination import LimitOffsetPagination, paginate

from apps.accounts.permissions import require_leadership

from .models import AuditLog

router = Router(tags=["audit"])


class AuditOut(Schema):
    id: int
    actor_id: int | None
    actor_name: str
    action: str
    target_type: str
    target_id: str
    target_label: str
    reason: str
    before: Any
    after: Any
    at: datetime


class AuditFilter(Schema):
    action: str | None = None  # exact code, or a prefix such as "membership."
    target_type: str | None = None
    target_id: str | None = None
    actor_id: int | None = None
    since: date | None = None  # inclusive, the viewer's calendar day sent as YYYY-MM-DD
    until: date | None = None  # inclusive
    q: str | None = None  # target label or reason contains


class ActorOut(Schema):
    user_id: int
    display_name: str


class FacetsOut(Schema):
    actions: list[str]
    target_types: list[str]
    actors: list[ActorOut]


@router.get("", response=list[AuditOut])
@paginate(LimitOffsetPagination)
def list_audit(request: HttpRequest, filters: Query[AuditFilter]):
    require_leadership(request.user)
    qs = AuditLog.objects.all()
    if filters.action:
        qs = qs.filter(action__startswith=filters.action)
    if filters.target_type:
        qs = qs.filter(target_type=filters.target_type)
    if filters.target_id:
        qs = qs.filter(target_id=filters.target_id)
    if filters.actor_id is not None:
        qs = qs.filter(actor_id=filters.actor_id)
    if filters.since:
        qs = qs.filter(at__date__gte=filters.since)
    if filters.until:
        qs = qs.filter(at__date__lte=filters.until)
    if filters.q:
        qs = qs.filter(Q(target_label__icontains=filters.q) | Q(reason__icontains=filters.q))
    return qs


@router.get("/facets", response=FacetsOut)
def facets(request: HttpRequest):
    """What the log contains, for the filter dropdowns: distinct actions, target types and actors."""
    require_leadership(request.user)
    actors = (
        AuditLog.objects.filter(actor__isnull=False)
        .values_list("actor_id", "actor__display_name")
        .distinct()
        .order_by("actor__display_name")
    )
    return {
        "actions": list(
            AuditLog.objects.order_by("action").values_list("action", flat=True).distinct()
        ),
        "target_types": list(
            AuditLog.objects.exclude(target_type="")
            .order_by("target_type")
            .values_list("target_type", flat=True)
            .distinct()
        ),
        "actors": [{"user_id": uid, "display_name": name} for uid, name in actors],
    }
