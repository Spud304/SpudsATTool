"""Scrim sessions and attendance. Sets, rounds and the live stream arrive in part B."""

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record
from apps.rules import selection
from apps.rules.models import Ruleset, TablePurpose

from . import events
from .models import (
    Attendance,
    Opponent,
    Pilot,
    PilotStatus,
    Rsvp,
    Session,
    SessionAttendance,
    SessionKind,
    Side,
)
from .roster import ScrimError

_UNSET = object()


def scope(session: Session) -> str:
    """Audit scope for everything that happens on one scrim."""
    return f"scrims.session:{session.pk}"


def _opponent(opponent_id: int | None) -> Opponent | None:
    if opponent_id is None:
        return None
    opponent = Opponent.objects.filter(pk=opponent_id).first()
    if opponent is None:
        raise ScrimError(422, f"unknown opponent {opponent_id}")
    return opponent


def _stage(ruleset: Ruleset, code: str | None):
    if not code:
        return None
    stage = ruleset.stages.filter(code=code).first()
    if stage is None:
        raise ScrimError(422, f"ruleset {ruleset.code} has no stage {code!r}")
    return stage


def _check_choices(value: str, choices, label: str) -> str:
    if value not in choices.values:
        raise ScrimError(422, f"unknown {label} {value!r}")
    return value


def create_session(
    actor: User,
    *,
    title: str,
    date: datetime,
    kind: str = SessionKind.PRACTICE,
    opponent_id: int | None = None,
    stage_code: str | None = None,
    system_name: str = "",
    moveme_system: str = "",
    motd: str = "",
    default_our_side: str = "",
) -> Session:
    ruleset = selection.active_ruleset()
    if ruleset is None:
        raise ScrimError(422, "no ruleset imported; import one before creating scrims")
    version = ruleset.point_versions.filter(purpose=TablePurpose.COST, is_current=True).first()
    if version is None:
        raise ScrimError(422, f"{ruleset.code} has no current cost table")
    title = title.strip()[:120]
    if not title:
        raise ScrimError(422, "title is required")
    _check_choices(kind, SessionKind, "kind")
    if default_our_side:
        _check_choices(default_our_side, Side, "side")
    with transaction.atomic():
        session = Session.objects.create(
            ruleset=ruleset,
            stage=_stage(ruleset, stage_code),
            point_table_version=version,
            kind=kind,
            title=title,
            date=date,
            opponent=_opponent(opponent_id),
            system_name=system_name.strip()[:60],
            moveme_system=moveme_system.strip()[:60],
            motd=motd,
            default_our_side=default_our_side,
            created_by=actor,
        )
        SessionAttendance.objects.bulk_create(
            SessionAttendance(session=session, pilot=pilot)
            for pilot in Pilot.objects.filter(status=PilotStatus.ACTIVE)
        )
    record(
        actor=actor,
        scope=scope(session),
        action="scrim.created",
        target=session,
        after=_snapshot(session),
    )
    return session


def _snapshot(session: Session) -> dict:
    return {
        "title": session.title,
        "date": session.date.isoformat(),
        "kind": session.kind,
        "opponent": session.opponent.name if session.opponent else None,
        "stage": session.stage.code if session.stage else None,
        "system": session.system_name,
        "side": session.default_our_side,
    }


def _require_not_archived(session: Session) -> None:
    if session.is_archived:
        raise ScrimError(409, "this scrim is archived and read-only")


def update_session(actor: User, session: Session, **fields) -> Session:
    _require_not_archived(session)
    before = _snapshot(session)
    if "title" in fields:
        title = (fields.pop("title") or "").strip()[:120]
        if not title:
            raise ScrimError(422, "title is required")
        session.title = title
    if "kind" in fields:
        session.kind = _check_choices(fields.pop("kind"), SessionKind, "kind")
    if "default_our_side" in fields:
        side = fields.pop("default_our_side") or ""
        session.default_our_side = _check_choices(side, Side, "side") if side else ""
    if "opponent_id" in fields:
        session.opponent = _opponent(fields.pop("opponent_id"))
    if "stage_code" in fields:
        session.stage = _stage(session.ruleset, fields.pop("stage_code"))
    for key, value in fields.items():
        if key in ("system_name", "moveme_system"):
            value = (value or "").strip()[:60]
        setattr(session, key, value)
    # Named fields only: the live stream owns `event_seq`, and this copy of the row may be stale.
    session.save(
        update_fields=[
            "title",
            "kind",
            "default_our_side",
            "opponent",
            "stage",
            "system_name",
            "moveme_system",
            "motd",
            "date",
            "updated_at",
        ]
    )
    after = _snapshot(session)
    diff = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    if diff or "motd" in fields:
        record(
            actor=actor,
            scope=scope(session),
            action="scrim.updated",
            target=session,
            before={k: v[0] for k, v in diff.items()},
            after={k: v[1] for k, v in diff.items()},
        )
    events.notify(session.pk, events.KIND_SESSION, actor)
    return session


def archive_session(actor: User, session: Session, reason: str = "") -> Session:
    if not session.is_archived:
        session.is_archived = True
        session.save(update_fields=["is_archived", "updated_at"])
        record(
            actor=actor,
            scope=scope(session),
            action="scrim.archived",
            target=session,
            reason=reason,
        )
    events.notify(session.pk, events.KIND_SESSION, actor)
    return session


def pilot_of(user: User) -> Pilot | None:
    return Pilot.objects.filter(user=user).first()


# A scrim counts as over this long after its start time. Comparing instants avoids the server's
# UTC calendar day flipping a 7 pm US-evening scrim into "yesterday" at 8 pm local.
PAST_AFTER = timedelta(hours=8)


def past_cutoff():
    return timezone.now() - PAST_AFTER


def is_past(session: Session) -> bool:
    return session.date < past_cutoff()


def set_rsvp(actor: User, session: Session, rsvp: str, reason: str = "") -> SessionAttendance:
    pilot = pilot_of(actor)
    if pilot is None:
        raise ScrimError(403, "your login is not linked to a pilot on the roster")
    _check_choices(rsvp, Rsvp, "rsvp")
    if is_past(session) or session.is_archived:
        raise ScrimError(409, "this scrim is over; RSVP is closed")
    reason = reason.strip()[:200]
    if rsvp == Rsvp.MAYBE and not reason:
        raise ScrimError(422, "say why when answering maybe")
    row, _ = SessionAttendance.objects.get_or_create(session=session, pilot=pilot)
    row.rsvp = rsvp
    row.rsvp_reason = reason if rsvp in (Rsvp.MAYBE, Rsvp.NO) else ""
    row.rsvp_at = timezone.now()
    row.save(update_fields=["rsvp", "rsvp_reason", "rsvp_at"])
    events.notify(session.pk, events.KIND_ATTENDANCE, actor)
    return row


def set_attendance(
    actor: User, session: Session, pilot: Pilot, attendance: str, reason: str = ""
) -> SessionAttendance:
    _require_not_archived(session)
    _check_choices(attendance, Attendance, "attendance")
    reason = reason.strip()[:200]
    row, _ = SessionAttendance.objects.get_or_create(session=session, pilot=pilot)
    before = row.attendance
    row.attendance = attendance
    if attendance == Attendance.NO_SHOW:
        if not reason:
            raise ScrimError(422, "a reason is required to mark a no-show")
        row.removed_by, row.removed_reason, row.removed_at = actor, reason, timezone.now()
    elif before == Attendance.NO_SHOW:
        row.removed_by, row.removed_reason, row.removed_at = None, "", None
    row.save()
    if attendance == Attendance.NO_SHOW:
        record(
            actor=actor,
            scope=scope(session),
            action="scrim.no_show_removed",
            target=session,
            reason=reason,
            after={"pilot": pilot.name},
        )
    elif before != attendance:
        record(
            actor=actor,
            scope=scope(session),
            action="scrim.attendance_set",
            target=session,
            after={"pilot": pilot.name, "attendance": attendance},
        )
    events.notify(session.pk, events.KIND_ATTENDANCE, actor)
    return row


def tally(session: Session) -> dict[str, int]:
    counts = dict.fromkeys(Rsvp.values, 0)
    for value in session.attendance.values_list("rsvp", flat=True):
        counts[value] += 1
    return counts


def queryset():
    return Session.objects.select_related(
        "ruleset__tournament", "stage", "opponent", "created_by"
    ).prefetch_related("attendance__pilot__user")
