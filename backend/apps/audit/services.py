from typing import Any

from django.db import models

from .models import AuditLog


def record(
    *,
    actor,
    action: str,
    target: models.Model | None = None,
    target_type: str = "",
    target_id: str = "",
    target_label: str = "",
    reason: str = "",
    before: Any = None,
    after: Any = None,
    scope: str = "",
) -> AuditLog:
    if target is not None:
        target_type = target_type or target._meta.label_lower
        target_id = target_id or str(target.pk)
        target_label = target_label or str(target)
    user = actor if getattr(actor, "is_authenticated", False) else None
    return AuditLog.objects.create(
        actor=user,
        actor_name=str(user) if user else "system",
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label[:200],
        reason=reason,
        before=before,
        after=after,
        scope=scope,
    )
