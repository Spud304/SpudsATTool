"""Sets, bans, rounds and lineups under /api/scrims/{session_id}/sets, plus the presence heartbeat.

Every write answers with the full set document; the same document goes out on the event stream.
"""

from typing import cast

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.accounts.models import User
from apps.rules.api import ViolationOut

from . import derived, presence, sets
from .models import Assignment, LineupSide, Session
from .roster import ScrimError

router = Router(tags=["scrims"])


# document schemas


class SlotDocOut(Schema):
    id: int
    slot_no: int
    pilot_id: int | None
    pilot_name: str | None
    pilot_user_id: int | None
    opp_pilot_name: str
    type_id: int | None
    ship_name: str | None
    hull_size: str | None
    is_flagship: bool
    is_unique: bool
    warp_in_km: int | None
    fit_id: int | None
    fit_name: str | None
    fit_text: str
    load_default: bool
    custom_note: str
    repeat_note: str
    link_scripts: list[str]
    died: bool
    has_links: bool
    base_points: int
    inflation_points: int
    total_points: int
    is_banned: bool
    link_index: int | None
    flags: list[str]


class SideDocOut(Schema):
    slots: list[SlotDocOut]
    total_points: int
    point_cap: int
    cap_status: str
    unspent_points: int
    is_legal: bool
    violations: list[ViolationOut]
    points_lost: int
    dead_count: int


class SideScoreOut(Schema):
    fielded_points: int
    unspent_points: int
    points_lost: int
    handicap_conceded: int
    points_conceded: int


class ScoreOut(Schema):
    us: SideScoreOut
    opp: SideScoreOut
    differential: int
    leader: str
    indicator: str
    point_threshold: int | None


class RoundDocOut(Schema):
    id: int
    round_no: int
    outcome: str
    notes: str
    banned_type_ids: list[int]
    us: SideDocOut
    opp: SideDocOut
    score: ScoreOut


class BanChipOut(Schema):
    id: int | None
    order: int | None
    side: str
    is_ours: bool
    kind: str
    index: int
    type_id: int | None
    ship_name: str | None
    in_effect_from_round: int


class RecordOut(Schema):
    wins: int
    losses: int
    draws: int


class SetDocOut(Schema):
    id: int
    index: int
    label: str
    comp_id: int | None
    comp_name: str | None
    our_archetype_id: int | None
    opp_archetype_id: int | None
    our_side: str
    tactics_note: str
    link_note: str
    warp_calls: list[str]
    bans: list[BanChipOut]
    avalanche_bans: list[BanChipOut]
    bans_per_side: int
    bans_are_blind: bool
    avalanche_enabled: bool
    extra_bans_owed: int
    rounds: list[RoundDocOut]
    record: RecordOut


# inputs


class SetCreateIn(Schema):
    copy_previous: bool = True
    label: str = ""


class SetPatchIn(Schema):
    label: str | None = None
    comp_id: int | None = None
    our_archetype_id: int | None = None
    opp_archetype_id: int | None = None
    our_side: str | None = None
    tactics_note: str | None = None
    link_note: str | None = None
    warp_calls: list[str] | None = None


class DeleteIn(Schema):
    reason: str = ""


class SetBanIn(Schema):
    side: str
    kind: str = "standard"
    index: int
    type_id: int | None = None
    in_effect_from_round: int = 1


class RoundPatchIn(Schema):
    outcome: str | None = None
    notes: str | None = None


class AssignmentPatchIn(Schema):
    pilot_id: int | None = None
    opp_pilot_name: str | None = None
    type_id: int | None = None
    is_flagship: bool | None = None
    is_unique: bool | None = None
    warp_in_km: int | None = None
    fit_id: int | None = None
    load_default: bool | None = None
    custom_note: str | None = None
    link_scripts: list[str] | None = None
    died: bool | None = None


class PasteIn(Schema):
    text: str


class PasteOut(Schema):
    set: SetDocOut
    unresolved: list[str]


class PresenceIn(Schema):
    focus: str | None = None


class ViewerOut(Schema):
    user_id: int
    name: str
    focus: str | None
    at: str


# helpers


def _session(session_id: int) -> Session:
    return get_object_or_404(Session.objects.select_related("ruleset", "stage"), pk=session_id)


def _wrap(call):
    try:
        return call()
    except ScrimError as exc:
        raise HttpError(exc.status, str(exc)) from exc


def _editor(request: HttpRequest, session: Session) -> User:
    permissions.require_view_session(request.user, session)
    permissions.require_edit_sets(request.user)
    return cast(User, request.user)


def _manager(request: HttpRequest, session: Session) -> User:
    permissions.require_view_session(request.user, session)
    permissions.require_manage_scrims(request.user)
    return cast(User, request.user)


# sets


@router.post("/{session_id}/sets", response={201: SetDocOut})
def create_set(request: HttpRequest, session_id: int, payload: SetCreateIn):
    user = _manager(request, _session(session_id))
    return 201, _wrap(
        lambda: sets.create_set(
            user, session_id, copy_previous=payload.copy_previous, label=payload.label
        )
    )


@router.patch("/{session_id}/sets/{set_id}", response=SetDocOut)
def patch_set(request: HttpRequest, session_id: int, set_id: int, payload: SetPatchIn):
    user = _editor(request, _session(session_id))
    fields = payload.dict(exclude_unset=True)
    return _wrap(lambda: sets.patch_set(user, session_id, set_id, **fields))


@router.delete("/{session_id}/sets/{set_id}", response={204: None})
def delete_set(request: HttpRequest, session_id: int, set_id: int, payload: DeleteIn):
    user = _manager(request, _session(session_id))
    _wrap(lambda: sets.delete_set(user, session_id, set_id, payload.reason))
    return 204, None


@router.post("/{session_id}/sets/{set_id}/bans", response=SetDocOut)
def put_ban(request: HttpRequest, session_id: int, set_id: int, payload: SetBanIn):
    user = _editor(request, _session(session_id))
    return _wrap(lambda: sets.put_ban(user, session_id, set_id, **payload.dict()))


# rounds


@router.post("/{session_id}/sets/{set_id}/rounds", response={201: SetDocOut})
def add_round(request: HttpRequest, session_id: int, set_id: int):
    user = _editor(request, _session(session_id))
    return 201, _wrap(lambda: sets.add_round(user, session_id, set_id))


@router.delete("/{session_id}/sets/{set_id}/rounds/{round_no}", response=SetDocOut)
def delete_round(request: HttpRequest, session_id: int, set_id: int, round_no: int):
    user = _manager(request, _session(session_id))
    return _wrap(lambda: sets.delete_round(user, session_id, set_id, round_no))


@router.patch("/{session_id}/sets/{set_id}/rounds/{round_no}", response=SetDocOut)
def patch_round(
    request: HttpRequest, session_id: int, set_id: int, round_no: int, payload: RoundPatchIn
):
    session = _session(session_id)
    permissions.require_view_session(request.user, session)
    permissions.require_score(request.user)
    user = cast(User, request.user)
    fields = payload.dict(exclude_unset=True)
    return _wrap(lambda: sets.patch_round(user, session_id, set_id, round_no, **fields))


# assignments


def _own_slot(user: User, set_id: int, round_no: int, side: str, slot_no: int) -> bool:
    return Assignment.objects.filter(
        round__set_id=set_id, round__round_no=round_no, side=side, slot_no=slot_no, pilot__user=user
    ).exists()


@router.patch("/{session_id}/sets/{set_id}/rounds/{round_no}/{side}/{slot_no}", response=SetDocOut)
def patch_assignment(
    request: HttpRequest,
    session_id: int,
    set_id: int,
    round_no: int,
    side: str,
    slot_no: int,
    payload: AssignmentPatchIn,
):
    session = _session(session_id)
    permissions.require_view_session(request.user, session)
    user = cast(User, request.user)
    fields = payload.dict(exclude_unset=True)
    if not permissions.can_edit_sets(user):
        # Pilots: their own slot's fit and note, and death toggles when the team lets pilots score.
        allowed = set()
        if side == LineupSide.US and _own_slot(user, set_id, round_no, side, slot_no):
            allowed |= sets.PILOT_OWN_FIELDS
        if permissions.can_score(user):
            allowed.add("died")
        refused = sorted(set(fields) - allowed)
        if refused:
            raise HttpError(403, f"you may not change {', '.join(refused)} on this slot")
    return _wrap(
        lambda: sets.patch_assignment(user, session_id, set_id, round_no, side, slot_no, **fields)
    )


@router.post("/{session_id}/sets/{set_id}/rounds/{round_no}/opp-lineup", response=PasteOut)
def paste_opp_lineup(
    request: HttpRequest, session_id: int, set_id: int, round_no: int, payload: PasteIn
):
    user = _editor(request, _session(session_id))
    doc, unresolved = _wrap(
        lambda: sets.paste_opp_lineup(user, session_id, set_id, round_no, payload.text)
    )
    return {"set": doc, "unresolved": unresolved}


# presence


@router.post("/{session_id}/presence", response=list[ViewerOut])
def heartbeat(request: HttpRequest, session_id: int, payload: PresenceIn):
    session = _session(session_id)
    permissions.require_view_session(request.user, session)
    return presence.heartbeat(session_id, cast(User, request.user), payload.focus)


@router.delete("/{session_id}/presence", response=list[ViewerOut])
def leave(request: HttpRequest, session_id: int):
    session = _session(session_id)
    permissions.require_view_session(request.user, session)
    return presence.leave(session_id, cast(User, request.user))


def set_documents(session: Session) -> list[dict]:
    """Every set of a session as documents; used by the session detail endpoint."""
    ctx = derived.context_for(session)
    qs = session.sets.select_related("comp").prefetch_related(*derived.SET_PREFETCH)
    return [derived.set_document(ctx, s) for s in qs]
