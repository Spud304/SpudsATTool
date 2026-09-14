from datetime import datetime
from typing import Any

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
    action: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    actor_id: int | None = None


@router.get("", response=list[AuditOut])
@paginate(LimitOffsetPagination)
def list_audit(request: HttpRequest, filters: Query[AuditFilter]):
    require_leadership(request.user)
    qs = AuditLog.objects.all()
    for field, value in filters.dict(exclude_none=True).items():
        qs = qs.filter(**{field: value})
    return qs
