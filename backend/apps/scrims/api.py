"""Scrim sessions, RSVP and attendance, plus the pilot roster and opponent registry."""

from datetime import datetime
from typing import cast

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.accounts.models import User
from apps.rules import selection

from . import roster, sessions, share, suggestions
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
    WarpInLabel,
)
from .sets_api import SetDocOut, set_documents
from .sets_api import router as sets_router

router = Router(tags=["scrims"])
router.add_router("", sets_router)
pilots_router = Router(tags=["scrims"])
opponents_router = Router(tags=["scrims"])


# schemas


class PilotHistoryOut(Schema):
    pilot_id: int
    pilot_name: str
    flights: int
    last_date: str | None


class PilotOut(Schema):
    id: int
    name: str
    user_id: int | None
    user_name: str | None
    status: str
    is_merc: bool
    roles_text: str
    notes: str


class PilotIn(Schema):
    name: str
    is_merc: bool = False
    roles_text: str = ""
    notes: str = ""
    user_id: int | None = None


class PilotPatchIn(Schema):
    name: str | None = None
    status: str | None = None
    is_merc: bool | None = None
    roles_text: str | None = None
    notes: str | None = None
    user_id: int | None = None


class OpponentOut(Schema):
    id: int
    name: str
    notes: str
    alliance_id: int | None
    is_active: bool


class OpponentIn(Schema):
    name: str
    notes: str = ""
    alliance_id: int | None = None


class OpponentPatchIn(Schema):
    name: str | None = None
    notes: str | None = None
    alliance_id: int | None = None
    is_active: bool | None = None


class TallyOut(Schema):
    yes: int
    no: int
    maybe: int
    none: int


class SetSummaryOut(Schema):
    id: int
    index: int
    label: str
    comp_name: str | None
    outcomes: list[str]


class SessionSummaryOut(Schema):
    id: int
    title: str
    date: str
    kind: str
    opponent_id: int | None
    opponent_name: str | None
    system_name: str
    ruleset: str
    stage: str | None
    default_our_side: str
    is_archived: bool
    my_rsvp: str | None
    my_rsvp_reason: str
    tally: TallyOut
    sets: list[SetSummaryOut]
    created_by_name: str


class AttendanceOut(Schema):
    pilot_id: int
    pilot_name: str
    user_id: int | None
    rsvp: str
    rsvp_reason: str
    rsvp_at: str | None
    attendance: str
    removed_reason: str
    is_me: bool


class SessionOut(SessionSummaryOut):
    sets: list[SetDocOut]  # type: ignore[assignment]  # full documents here, summaries in lists
    moveme_system: str
    motd: str
    point_table_version: int | None
    attendance: list[AttendanceOut]
    event_seq: int
    can_manage: bool
    can_rsvp: bool


class SessionCreateIn(Schema):
    title: str
    date: datetime
    kind: str = SessionKind.PRACTICE
    opponent_id: int | None = None
    stage_code: str | None = None
    system_name: str = ""
    moveme_system: str = ""
    motd: str = ""
    default_our_side: str = ""


class SessionPatchIn(Schema):
    title: str | None = None
    date: datetime | None = None
    kind: str | None = None
    opponent_id: int | None = None
    stage_code: str | None = None
    system_name: str | None = None
    moveme_system: str | None = None
    motd: str | None = None
    default_our_side: str | None = None


class ArchiveIn(Schema):
    reason: str = ""


class RsvpIn(Schema):
    rsvp: str
    reason: str = ""


class AttendanceIn(Schema):
    attendance: str
    reason: str = ""


class StageOut(Schema):
    code: str
    label: str
    best_of: int
    bans_per_side: int


class VocabOut(Schema):
    warp_labels: list[str]
    kinds: list[str]
    sides: list[str]
    rsvps: list[str]
    attendance: list[str]
    stages: list[StageOut]
    active_ruleset: str | None


# serializers


def _pilot_out(p: Pilot) -> dict:
    return {
        "id": p.pk,
        "name": p.name,
        "user_id": p.user_id,
        "user_name": p.user.display_name if p.user else None,
        "status": p.status,
        "is_merc": p.is_merc,
        "roles_text": p.roles_text,
        "notes": p.notes,
    }


def _opponent_out(o: Opponent) -> dict:
    return {
        "id": o.pk,
        "name": o.name,
        "notes": o.notes,
        "alliance_id": o.alliance_id,
        "is_active": o.is_active,
    }


def _my_row(session: Session, user: User | None) -> SessionAttendance | None:
    if user is None:
        return None
    return next((a for a in session.attendance.all() if a.pilot.user_id == user.pk), None)


def _summary(session: Session, user: User | None, has_pilot: bool) -> dict:
    mine = _my_row(session, user)
    return {
        "id": session.pk,
        "title": session.title,
        "date": session.date.isoformat(),
        "kind": session.kind,
        "opponent_id": session.opponent_id,
        "opponent_name": session.opponent.name if session.opponent else None,
        "system_name": session.system_name,
        "ruleset": session.ruleset.code,
        "stage": session.stage.code if session.stage else None,
        "default_our_side": session.default_our_side,
        "is_archived": session.is_archived,
        "my_rsvp": mine.rsvp if mine else (Rsvp.NONE if has_pilot else None),
        "my_rsvp_reason": mine.rsvp_reason if mine else "",
        "tally": sessions.tally(session),
        "sets": [
            {
                "id": s.pk,
                "index": s.index,
                "label": s.label,
                "comp_name": s.comp.name if s.comp else None,
                "outcomes": [r.outcome for r in s.rounds.all()],
            }
            for s in session.sets.all()
        ],
        "created_by_name": session.created_by.display_name if session.created_by else "",
    }


def _attendance_rows(session: Session, user: User | None) -> list[dict]:
    order = {Rsvp.YES: 0, Rsvp.MAYBE: 1, Rsvp.NONE: 2, Rsvp.NO: 3}
    rows = sorted(session.attendance.all(), key=lambda a: (order[a.rsvp], a.pilot.name.lower()))
    return [
        {
            "pilot_id": a.pilot_id,
            "pilot_name": a.pilot.name,
            "user_id": a.pilot.user_id,
            "rsvp": a.rsvp,
            "rsvp_reason": a.rsvp_reason,
            "rsvp_at": a.rsvp_at.isoformat() if a.rsvp_at else None,
            "attendance": a.attendance,
            "removed_reason": a.removed_reason,
            "is_me": user is not None and a.pilot.user_id == user.pk,
        }
        for a in rows
    ]


def session_document(session: Session, user: User | None, shared: bool = False) -> dict:
    """The full scrim. `shared` is the public share-link view: no fit text, no permissions, nobody is "me"."""
    pilot = sessions.pilot_of(user) if user is not None else None
    sets = set_documents(session)
    if shared:
        sets = [share.strip_fit_text(doc) for doc in sets]
    return {
        **_summary(session, user, pilot is not None),
        "moveme_system": session.moveme_system,
        "motd": session.motd,
        "point_table_version": session.point_table_version_id,
        "attendance": _attendance_rows(session, user),
        "event_seq": session.event_seq,
        "sets": sets,
        "can_manage": user is not None and not shared and permissions.can_manage_scrims(user),
        "can_rsvp": pilot is not None and not shared and not sessions.is_past(session),
    }


def _full(session: Session, user: User) -> dict:
    return session_document(session, user)


def _session(session_id: int) -> Session:
    return get_object_or_404(
        sessions.queryset().prefetch_related("sets__comp", "sets__rounds"), pk=session_id
    )


def _wrap(call):
    try:
        return call()
    except roster.ScrimError as exc:
        raise HttpError(exc.status, str(exc)) from exc


# scrims


@router.get("", response=list[SessionSummaryOut])
def list_sessions(request: HttpRequest, when: str = "upcoming"):
    permissions.require_scrim_access(request.user)
    user = cast(User, request.user)
    qs = sessions.queryset().prefetch_related("sets__comp", "sets__rounds")
    cutoff = sessions.past_cutoff()
    if when == "upcoming":
        qs = qs.filter(date__gte=cutoff, is_archived=False).order_by("date")
    elif when == "past":
        qs = qs.filter(date__lt=cutoff) | qs.filter(is_archived=True)
        qs = qs.order_by("-date")
    elif when != "all":
        raise HttpError(422, "when must be upcoming, past or all")
    has_pilot = sessions.pilot_of(user) is not None
    return [_summary(s, user, has_pilot) for s in qs]


@router.post("", response={201: SessionOut})
def create_session(request: HttpRequest, payload: SessionCreateIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    session = _wrap(lambda: sessions.create_session(user, **payload.dict()))
    return 201, _full(_session(session.pk), user)


@router.get("/vocab", response=VocabOut)
def vocab(request: HttpRequest):
    permissions.require_scrim_access(request.user)
    active = selection.active_ruleset()
    stages = list(active.stages.all()) if active else []
    return {
        "warp_labels": list(
            WarpInLabel.objects.filter(is_active=True).values_list("label", flat=True)
        ),
        "kinds": list(SessionKind.values),
        "sides": list(Side.values),
        "rsvps": list(Rsvp.values),
        "attendance": list(Attendance.values),
        "stages": [
            {
                "code": s.code,
                "label": s.label,
                "best_of": s.best_of,
                "bans_per_side": s.bans_per_side,
            }
            for s in stages
        ],
        "active_ruleset": active.code if active else None,
    }


@router.get("/{session_id}", response=SessionOut)
def get_session(request: HttpRequest, session_id: int):
    session = _session(session_id)
    permissions.require_view_session(request.user, session)
    return _full(session, cast(User, request.user))


@router.patch("/{session_id}", response=SessionOut)
def patch_session(request: HttpRequest, session_id: int, payload: SessionPatchIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    session = _session(session_id)
    fields = payload.dict(exclude_unset=True)
    _wrap(lambda: sessions.update_session(user, session, **fields))
    return _full(_session(session.pk), user)


@router.post("/{session_id}/archive", response=SessionOut)
def archive_session(request: HttpRequest, session_id: int, payload: ArchiveIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    session = _session(session_id)
    sessions.archive_session(user, session, payload.reason)
    return _full(_session(session.pk), user)


@router.put("/{session_id}/rsvp", response=SessionOut)
def put_rsvp(request: HttpRequest, session_id: int, payload: RsvpIn):
    permissions.require_scrim_access(request.user)
    user = cast(User, request.user)
    session = _session(session_id)
    _wrap(lambda: sessions.set_rsvp(user, session, payload.rsvp, payload.reason))
    return _full(_session(session.pk), user)


@router.patch("/{session_id}/attendance/{pilot_id}", response=SessionOut)
def patch_attendance(request: HttpRequest, session_id: int, pilot_id: int, payload: AttendanceIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    session = _session(session_id)
    pilot = get_object_or_404(Pilot, pk=pilot_id)
    _wrap(lambda: sessions.set_attendance(user, session, pilot, payload.attendance, payload.reason))
    return _full(_session(session.pk), user)


# pilots


@pilots_router.get("/history", response=list[PilotHistoryOut])
def pilot_history(request: HttpRequest, type_id: int, exclude_session: int | None = None):
    """Who has flown this hull in past scrims, most flights first; feeds the pilot dropdown."""
    permissions.require_scrim_access(request.user)
    return suggestions.pilot_history(type_id, exclude_session)


@pilots_router.get("", response=list[PilotOut])
def list_pilots(request: HttpRequest, status: str | None = None):
    permissions.require_scrim_access(request.user)
    qs = Pilot.objects.select_related("user")
    if status:
        if status not in PilotStatus.values:
            raise HttpError(422, f"unknown status {status!r}")
        qs = qs.filter(status=status)
    return [_pilot_out(p) for p in qs]


@pilots_router.post("", response={201: PilotOut})
def create_pilot(request: HttpRequest, payload: PilotIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    pilot = _wrap(lambda: roster.create_pilot(user, **payload.dict()))
    return 201, _pilot_out(Pilot.objects.select_related("user").get(pk=pilot.pk))


@pilots_router.patch("/{pilot_id}", response=PilotOut)
def patch_pilot(request: HttpRequest, pilot_id: int, payload: PilotPatchIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    pilot = get_object_or_404(Pilot.objects.select_related("user"), pk=pilot_id)
    fields = payload.dict(exclude_unset=True)
    _wrap(lambda: roster.update_pilot(user, pilot, **fields))
    return _pilot_out(Pilot.objects.select_related("user").get(pk=pilot.pk))


# opponents


@opponents_router.get("", response=list[OpponentOut])
def list_opponents(request: HttpRequest):
    permissions.require_scrim_access(request.user)
    return [_opponent_out(o) for o in Opponent.objects.all()]


@opponents_router.post("", response={201: OpponentOut})
def create_opponent(request: HttpRequest, payload: OpponentIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    opponent = _wrap(lambda: roster.create_opponent(user, **payload.dict()))
    return 201, _opponent_out(opponent)


@opponents_router.patch("/{opponent_id}", response=OpponentOut)
def patch_opponent(request: HttpRequest, opponent_id: int, payload: OpponentPatchIn):
    permissions.require_manage_scrims(request.user)
    user = cast(User, request.user)
    opponent = get_object_or_404(Opponent, pk=opponent_id)
    fields = payload.dict(exclude_unset=True)
    return _opponent_out(_wrap(lambda: roster.update_opponent(user, opponent, **fields)))
