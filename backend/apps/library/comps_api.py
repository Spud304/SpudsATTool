"""Comp library endpoints at /api/comps. Static routes come before /{comp_id}."""

from dataclasses import asdict
from typing import cast

from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.accounts.models import User
from apps.rules import selection
from apps.rules.api import EvaluateOut
from apps.rules.engine import CompEvaluation
from apps.rules.models import Ruleset

from . import comps
from .constants import LINK_SCRIPTS
from .models import Archetype, Comp, CompStatus

router = Router(tags=["library"])


class CompSlotIn(Schema):
    slot_no: int
    type_id: int | None = None
    is_flagship: bool = False
    is_unique: bool = False
    warp_in_km: int | None = None
    default_fit_id: int | None = None
    ship_note: str = ""
    link_scripts: list[str] = []


class CompSlotOut(Schema):
    slot_no: int
    type_id: int | None
    ship_name: str | None
    is_flagship: bool
    is_unique: bool
    warp_in_km: int | None
    default_fit_id: int | None
    default_fit_name: str | None
    default_fit_status: str | None
    default_fit_has_links: bool
    default_fit_dps: float | None
    default_fit_ehp_k: float | None
    default_fit_speed_ms: float | None
    ship_note: str
    link_scripts: list[str]
    over_count: bool  # past the ruleset's pilot count (it went down); does not fly


class CompEvalSummaryOut(Schema):
    total_points: int
    point_cap: int
    cap_status: str
    is_legal: bool
    error_count: int
    banned_hulls: list[str]


class CompStatsOut(Schema):
    dps_total: float | None
    ehp_k_total: float | None
    speed_avg: float | None
    speed_min: float | None
    fits_set: int
    fits_with_stats: int


class CompSummaryOut(Schema):
    id: int
    ruleset: str
    name: str
    status: str
    archetype_id: int | None
    archetype: str | None
    hulls: list[str | None]
    evaluation: CompEvalSummaryOut | None
    stats: CompStatsOut
    created_by_id: int | None
    created_by_name: str
    updated_at: str


class CompOut(CompSummaryOut):
    notes: str
    ban_theory: str
    fielded_pilots: int
    flagship_enabled: bool
    slots: list[CompSlotOut]
    evaluation_detail: EvaluateOut | None
    reviewed_by_name: str
    reviewed_at: str | None
    can_edit: bool


class CompCreateIn(Schema):
    name: str
    ruleset: str | None = None
    status: str | None = None
    archetype_id: int | None = None
    notes: str = ""
    ban_theory: str = ""
    slots: list[CompSlotIn] | None = None


class CompPatchIn(Schema):
    name: str | None = None
    status: str | None = None
    archetype_id: int | None = None
    notes: str | None = None
    ban_theory: str | None = None
    slots: list[CompSlotIn] | None = None
    clear_over_count: bool | None = None  # delete the slots past the ruleset's pilot count
    reason: str = ""


class CloneIn(Schema):
    name: str | None = None
    ruleset: str | None = None


class ArchetypeOut(Schema):
    id: int
    name: str
    description: str
    is_retired: bool
    sort_order: int
    in_use: int = 0


class ArchetypeIn(Schema):
    name: str
    description: str = ""
    sort_order: int = 0


class ArchetypePatchIn(Schema):
    name: str | None = None
    description: str | None = None
    is_retired: bool | None = None
    sort_order: int | None = None


class LinkScriptOut(Schema):
    code: str
    name: str
    family: str


class CompVocabOut(Schema):
    link_scripts: list[LinkScriptOut]
    archetypes: list[ArchetypeOut]
    statuses: list[str]
    active_ruleset: str | None


def _ruleset(code: str) -> Ruleset:
    return get_object_or_404(Ruleset.objects.select_related("tournament"), tournament__code=code)


def _parse_banned(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return ()
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise HttpError(422, f"banned must be type ids, got {part!r}")
        out.append(int(part))
    return tuple(out)


def _can_edit(user: User, comp: Comp) -> bool:
    if permissions.can_manage_library(user):
        return True
    return (
        permissions.can_suggest_library(user)
        and comp.created_by_id == user.pk
        and comp.status == CompStatus.SUGGESTED
    )


def _summary(comp: Comp, banned: tuple[int, ...] = ()) -> tuple[dict, CompEvaluation | None]:
    evaluation = comps.evaluate(comp, banned)
    summary = None
    if evaluation is not None:
        banned_hulls = sorted(
            {s.name for s in evaluation.slots if s.is_banned and s.name is not None}
        )
        summary = {
            "total_points": evaluation.total_points,
            "point_cap": evaluation.point_cap,
            "cap_status": evaluation.cap_status,
            "is_legal": evaluation.is_legal,
            "error_count": sum(1 for v in evaluation.violations if v.severity == "error"),
            "banned_hulls": banned_hulls,
        }
    return {
        "id": comp.pk,
        "ruleset": comp.ruleset.code,
        "name": comp.name,
        "status": comp.status,
        "archetype_id": comp.archetype_id,
        "archetype": comp.archetype.name if comp.archetype else None,
        "hulls": [s.ship.name if s.ship else None for s in comp.slots.all()],
        "evaluation": summary,
        "stats": comps.comp_stats(comp),
        "created_by_id": comp.created_by_id,
        "created_by_name": comp.created_by.display_name if comp.created_by else "",
        "updated_at": comp.updated_at.isoformat(),
    }, evaluation


def _slot_out(slot, fielded: int) -> dict:
    fit = slot.default_fit
    return {
        "slot_no": slot.slot_no,
        "type_id": slot.ship_id,
        "ship_name": slot.ship.name if slot.ship else None,
        "is_flagship": slot.is_flagship,
        "is_unique": slot.is_unique,
        "warp_in_km": slot.warp_in_km,
        "default_fit_id": slot.default_fit_id,
        "default_fit_name": fit.name if fit else None,
        "default_fit_status": fit.status if fit else None,
        "default_fit_has_links": bool(fit and fit.has_links),
        "default_fit_dps": fit.dps if fit else None,
        "default_fit_ehp_k": fit.ehp_k if fit else None,
        "default_fit_speed_ms": fit.speed_ms if fit else None,
        "ship_note": slot.ship_note,
        "link_scripts": list(slot.link_scripts or []),
        "over_count": slot.slot_no > fielded,
    }


def _full(comp: Comp, user: User) -> dict:
    summary, evaluation = _summary(comp)
    return {
        **summary,
        "notes": comp.notes,
        "ban_theory": comp.ban_theory,
        "fielded_pilots": comp.ruleset.fielded_pilots,
        "flagship_enabled": comp.ruleset.flagship_enabled,
        "slots": [_slot_out(s, comp.ruleset.fielded_pilots) for s in comp.slots.all()],
        "evaluation_detail": asdict(evaluation) if evaluation is not None else None,
        "reviewed_by_name": comp.reviewed_by.display_name if comp.reviewed_by else "",
        "reviewed_at": comp.reviewed_at.isoformat() if comp.reviewed_at else None,
        "can_edit": _can_edit(user, comp),
    }


def _comp(comp_id: int) -> Comp:
    return get_object_or_404(comps.queryset(), pk=comp_id)


def _archetype_out(a: Archetype) -> dict:
    return {
        "id": a.pk,
        "name": a.name,
        "description": a.description,
        "is_retired": a.is_retired,
        "sort_order": a.sort_order,
        "in_use": comps.archetype_uses(a),
    }


def _slot_patches(slots: list[CompSlotIn] | None) -> list[comps.SlotPatch] | None:
    if slots is None:
        return None
    return [
        comps.SlotPatch(
            slot_no=sl.slot_no,
            type_id=sl.type_id,
            is_flagship=sl.is_flagship,
            is_unique=sl.is_unique,
            warp_in_km=sl.warp_in_km,
            default_fit_id=sl.default_fit_id,
            ship_note=sl.ship_note,
            link_scripts=tuple(sl.link_scripts),
        )
        for sl in slots
    ]


def _wrap(call):
    try:
        return call()
    except comps.FitError as exc:
        raise HttpError(exc.status, str(exc)) from exc


@router.get("", response=list[CompSummaryOut])
def list_comps(
    request: HttpRequest,
    ruleset: str | None = None,
    status: str | None = None,
    archetype: int | None = None,
    q: str | None = None,
    banned: str | None = None,
):
    permissions.require_browse_library(request.user)
    banned_ids = _parse_banned(banned)
    qs = comps.queryset()
    if ruleset:
        qs = qs.filter(ruleset__tournament__code=ruleset)
    else:
        active = selection.active_ruleset()
        if active is None:
            return []
        qs = qs.filter(ruleset=active)
    if status:
        qs = qs.filter(status__in=[s.strip() for s in status.split(",") if s.strip()])
    if archetype is not None:
        qs = qs.filter(archetype_id=archetype)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(slots__ship__name__icontains=q)).distinct()
    return [_summary(c, banned_ids)[0] for c in qs]


@router.post("", response={201: CompOut})
def create_comp(request: HttpRequest, payload: CompCreateIn):
    permissions.require_browse_library(request.user)
    permissions.require_add_to_library(request.user)
    user = cast(User, request.user)
    ruleset = _ruleset(payload.ruleset) if payload.ruleset else None
    comp = _wrap(
        lambda: comps.create_comp(
            user,
            name=payload.name,
            ruleset=ruleset,
            status=payload.status,
            archetype_id=payload.archetype_id,
            notes=payload.notes,
            ban_theory=payload.ban_theory,
            slots=_slot_patches(payload.slots),
        )
    )
    return 201, _full(_comp(comp.pk), user)


@router.get("/vocab", response=CompVocabOut)
def vocab(request: HttpRequest):
    permissions.require_browse_library(request.user)
    active = selection.active_ruleset()
    return {
        "link_scripts": [
            {"code": code, "name": name, "family": family}
            for code, (name, family) in LINK_SCRIPTS.items()
        ],
        "archetypes": [_archetype_out(a) for a in Archetype.objects.all()],
        "statuses": list(CompStatus.values),
        "active_ruleset": active.code if active else None,
    }


@router.post("/archetypes", response={201: ArchetypeOut})
def create_archetype(request: HttpRequest, payload: ArchetypeIn):
    permissions.require_browse_library(request.user)
    user = cast(User, request.user)
    if not permissions.can_manage_library(user):
        raise HttpError(403, "only theorycrafters and above edit archetypes")
    archetype = _wrap(lambda: comps.create_archetype(user, **payload.dict()))
    return 201, _archetype_out(archetype)


@router.patch("/archetypes/{archetype_id}", response=ArchetypeOut)
def patch_archetype(request: HttpRequest, archetype_id: int, payload: ArchetypePatchIn):
    permissions.require_browse_library(request.user)
    user = cast(User, request.user)
    if not permissions.can_manage_library(user):
        raise HttpError(403, "only theorycrafters and above edit archetypes")
    archetype = get_object_or_404(Archetype, pk=archetype_id)
    fields = payload.dict(exclude_unset=True)
    return _archetype_out(_wrap(lambda: comps.update_archetype(user, archetype, **fields)))


@router.delete("/archetypes/{archetype_id}", response={204: None})
def delete_archetype(request: HttpRequest, archetype_id: int):
    permissions.require_browse_library(request.user)
    user = cast(User, request.user)
    if not permissions.can_manage_library(user):
        raise HttpError(403, "only theorycrafters and above edit archetypes")
    archetype = get_object_or_404(Archetype, pk=archetype_id)
    _wrap(lambda: comps.delete_archetype(user, archetype))
    return 204, None


@router.get("/{comp_id}", response=CompOut)
def get_comp(request: HttpRequest, comp_id: int):
    permissions.require_browse_library(request.user)
    return _full(_comp(comp_id), cast(User, request.user))


@router.patch("/{comp_id}", response=CompOut)
def patch_comp(request: HttpRequest, comp_id: int, payload: CompPatchIn):
    permissions.require_browse_library(request.user)
    user = cast(User, request.user)
    comp = _comp(comp_id)
    if not _can_edit(user, comp):
        raise HttpError(403, "you can only edit your own suggested comps")
    fields = payload.dict(exclude_unset=True)
    slots = _slot_patches(payload.slots)
    _wrap(
        lambda: comps.update_comp(
            user,
            comp,
            name=payload.name,
            status=payload.status,
            archetype_id=fields.get("archetype_id", comps.UNSET),
            notes=payload.notes,
            ban_theory=payload.ban_theory,
            slots=slots,
            clear_over_count=bool(payload.clear_over_count),
            reason=payload.reason,
        )
    )
    return _full(_comp(comp.pk), user)


@router.post("/{comp_id}/clone", response={201: CompOut})
def clone_comp(request: HttpRequest, comp_id: int, payload: CloneIn):
    permissions.require_browse_library(request.user)
    permissions.require_add_to_library(request.user)
    user = cast(User, request.user)
    comp = _comp(comp_id)
    ruleset = _ruleset(payload.ruleset) if payload.ruleset else None
    new = _wrap(lambda: comps.clone_comp(user, comp, name=payload.name, ruleset=ruleset))
    return 201, _full(_comp(new.pk), user)
