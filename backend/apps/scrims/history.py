"""One scrim's history: its audit rows plus the soft-deleted sets and rounds a captain can restore."""

from apps.audit.models import AuditLog

from .models import Round, Session, Set
from .sessions import scope
from .sets import round_restorable

HISTORY_LIMIT = 200


def history_document(session: Session) -> dict:
    entries = AuditLog.objects.filter(scope=scope(session)).select_related("actor")[:HISTORY_LIMIT]
    deleted_sets = (
        Set.all_objects.filter(session=session, deleted_at__isnull=False)
        .select_related("comp", "deleted_by")
        .order_by("index")
    )
    deleted_rounds = (
        Round.all_objects.filter(
            set__session=session, set__deleted_at__isnull=True, deleted_at__isnull=False
        )
        .select_related("set", "deleted_by")
        .order_by("set__index", "round_no")
    )
    return {
        "entries": [
            {
                "id": e.pk,
                "actor_name": e.actor_name,
                "action": e.action,
                "target_label": e.target_label,
                "reason": e.reason,
                "after": e.after if isinstance(e.after, dict) else None,
                "at": e.at.isoformat(),
            }
            for e in entries
        ],
        "deleted_sets": [
            {
                "id": s.pk,
                "index": s.index,
                "comp_name": s.comp.name if s.comp else None,
                "rounds": Round.all_objects.filter(set=s).count(),
                "deleted_at": s.deleted_at.isoformat() if s.deleted_at else "",
                "deleted_by_name": s.deleted_by.display_name if s.deleted_by else "",
            }
            for s in deleted_sets
        ],
        "deleted_rounds": [
            {
                "set_id": r.set_id,
                "set_index": r.set.index,
                "round_no": r.round_no,
                "deleted_at": r.deleted_at.isoformat() if r.deleted_at else "",
                "deleted_by_name": r.deleted_by.display_name if r.deleted_by else "",
                "restorable": round_restorable(r.set, r),
            }
            for r in deleted_rounds
        ],
    }
