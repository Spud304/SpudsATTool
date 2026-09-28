"""Pilots and opponents. Pilots are auto-created for members; captains add mercs and alumni by hand."""

from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.audit.services import record

from .models import Opponent, Pilot, PilotStatus


class ScrimError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _display_name(user: User) -> str:
    main = user.main_character
    if main is not None:
        return main.name
    character = user.characters.order_by("created_at").first()
    return character.name if character is not None else user.display_name or user.username


def attach_to_upcoming(pilot: Pilot) -> int:
    """Put a pilot on the roll call of every scrim still to come, so late joiners can RSVP. Idempotent."""
    from . import events, sessions
    from .models import Session, SessionAttendance

    upcoming = Session.objects.filter(is_archived=False, date__gte=sessions.past_cutoff()).exclude(
        attendance__pilot=pilot
    )
    session_ids = list(upcoming.values_list("pk", flat=True))
    if not session_ids:
        return 0
    SessionAttendance.objects.bulk_create(
        [SessionAttendance(session_id=sid, pilot=pilot) for sid in session_ids],
        ignore_conflicts=True,
    )
    for sid in session_ids:
        events.notify(sid, events.KIND_ATTENDANCE)
    return len(session_ids)


def ensure_pilot_for(user: User) -> Pilot:
    """Idempotent: the member's pilot row, adopting an unlinked row with the same name if one exists."""
    existing = Pilot.objects.filter(user=user).first()
    if existing is not None:
        return existing
    name = _display_name(user)[:100]
    unlinked = Pilot.objects.filter(name__iexact=name, user__isnull=True).first()
    if unlinked is not None:
        unlinked.user = user
        unlinked.status = PilotStatus.ACTIVE
        unlinked.save(update_fields=["user", "status", "updated_at"])
        attach_to_upcoming(unlinked)
        return unlinked
    try:
        with transaction.atomic():
            pilot = Pilot.objects.create(name=name, user=user)
    except IntegrityError:
        raced = Pilot.objects.filter(user=user).first()
        if raced is not None:  # a concurrent call created this member's pilot first
            return raced
        # a different login already owns that name: keep both, make ours unique
        pilot = Pilot.objects.create(name=f"{name} ({user.pk})"[:100], user=user)
    attach_to_upcoming(pilot)
    return pilot


def create_pilot(
    actor: User,
    *,
    name: str,
    is_merc: bool = False,
    roles_text: str = "",
    notes: str = "",
    user_id: int | None = None,
) -> Pilot:
    name = name.strip()[:100]
    if not name:
        raise ScrimError(422, "pilot name is required")
    user = _linkable_user(user_id) if user_id is not None else None
    try:
        with transaction.atomic():
            pilot = Pilot.objects.create(
                name=name, is_merc=is_merc, roles_text=roles_text, notes=notes, user=user
            )
    except IntegrityError as exc:
        raise ScrimError(409, f"a pilot named {name!r} already exists") from exc
    attach_to_upcoming(pilot)
    record(actor=actor, action="pilot.created", target=pilot, after={"name": name, "merc": is_merc})
    return pilot


def _linkable_user(user_id: int, pilot: Pilot | None = None) -> User:
    """`pilot` is the row being edited: already being linked to it is not a clash."""
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise ScrimError(422, f"unknown user {user_id}")
    others = Pilot.objects.filter(user=user)
    if pilot is not None:
        others = others.exclude(pk=pilot.pk)
    if others.exists():
        raise ScrimError(409, f"{user.display_name} is already linked to a pilot")
    return user


def update_pilot(actor: User, pilot: Pilot, **fields) -> Pilot:
    before = {k: getattr(pilot, k) for k in fields if k != "user_id"}
    if "user_id" in fields:
        user_id = fields.pop("user_id")
        before["user"] = pilot.user.display_name if pilot.user else None
        pilot.user = _linkable_user(user_id, pilot) if user_id is not None else None
    for key, value in fields.items():
        if key == "name":
            value = value.strip()[:100]
            if not value:
                raise ScrimError(422, "pilot name is required")
        if key == "status" and value not in PilotStatus.values:
            raise ScrimError(422, f"unknown status {value!r}")
        setattr(pilot, key, value)
    try:
        with transaction.atomic():
            pilot.save()
    except IntegrityError as exc:
        raise ScrimError(409, f"a pilot named {pilot.name!r} already exists") from exc
    if fields.get("status") == PilotStatus.ACTIVE and before.get("status") != PilotStatus.ACTIVE:
        attach_to_upcoming(pilot)  # back on the roster: back on the roll call
    after = {k: getattr(pilot, k) for k in before if k != "user"}
    if "user" in before:
        after["user"] = pilot.user.display_name if pilot.user else None
    record(actor=actor, action="pilot.updated", target=pilot, before=before, after=after)
    return pilot


def create_opponent(
    actor: User, *, name: str, notes: str = "", alliance_id: int | None = None
) -> Opponent:
    name = name.strip()[:100]
    if not name:
        raise ScrimError(422, "opponent name is required")
    try:
        with transaction.atomic():
            opponent = Opponent.objects.create(name=name, notes=notes, alliance_id=alliance_id)
    except IntegrityError as exc:
        raise ScrimError(409, f"an opponent named {name!r} already exists") from exc
    record(actor=actor, action="opponent.created", target=opponent, after={"name": name})
    return opponent


def update_opponent(actor: User, opponent: Opponent, **fields) -> Opponent:
    before = {k: getattr(opponent, k) for k in fields}
    if "name" in fields:
        fields["name"] = (fields["name"] or "").strip()[:100]
        if not fields["name"]:
            raise ScrimError(422, "opponent name is required")
    for key, value in fields.items():
        setattr(opponent, key, value)
    try:
        with transaction.atomic():
            opponent.save()
    except IntegrityError as exc:
        raise ScrimError(409, f"an opponent named {opponent.name!r} already exists") from exc
    record(actor=actor, action="opponent.updated", target=opponent, before=before, after=fields)
    return opponent
