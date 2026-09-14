"""Fit library endpoints. Browsing needs the library capability; writing follows services._check_status."""

from typing import cast

from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.accounts.models import User
from apps.rules.models import Ruleset

from . import services
from .models import Fit, FitStatus

router = Router(tags=["library"])


class FitSummaryOut(Schema):
    id: int
    ship_id: int
    ship_name: str
    name: str
    status: str
    dps: float | None
    volley: float | None
    ehp_k: float | None
    speed_ms: float | None
    sig_radius_m: float | None
    cap_stable_pct: float | None
    cap_lasts_s: int | None
    targeting_range_km: float | None
    stats_parse_ok: bool
    has_links: bool
    unresolved_count: int
    created_by_id: int | None
    created_by_name: str
    created_at: str
    updated_at: str


class FitOut(FitSummaryOut):
    eft_text: str
    pyfa_summary: str
    unresolved_names: list[str]
    reviewed_by_name: str
    reviewed_at: str | None
    can_edit: bool


class FitCreateIn(Schema):
    eft_text: str
    name: str | None = None
    pyfa_summary: str = ""
    status: str | None = None


class FitPatchIn(Schema):
    name: str | None = None
    eft_text: str | None = None
    pyfa_summary: str | None = None
    status: str | None = None
    reason: str = ""


class ParseIn(Schema):
    eft_text: str
    pyfa_summary: str = ""


class ParseItemOut(Schema):
    line_no: int
    name: str
    charge: str | None
    quantity: int
    offline: bool
    type_id: int | None
    group_name: str | None
    category_name: str | None
    meta_group_name: str | None
    meta_level: int | None
    charge_type_id: int | None


class StatsOut(Schema):
    dps: float | None
    volley: float | None
    ehp_k: float | None
    speed_ms: float | None
    sig_radius_m: float | None
    cap_stable_pct: float | None
    cap_lasts_s: int | None
    targeting_range_km: float | None
    ok: bool


class ParseOut(Schema):
    ok: bool
    hull_name: str
    hull_type_id: int | None
    fit_name: str
    items: list[ParseItemOut]
    unresolved: list[str]
    has_links: bool
    stats: StatsOut
    warnings: list[str]
    errors: list[str]


class FitViolationOut(Schema):
    code: str
    severity: str
    message: str
    line_nos: list[int]
    data: dict[str, int | str]


class LegalityOut(Schema):
    ruleset: str
    revision: int
    is_flagship: bool
    is_legal: bool
    item_count: int
    violations: list[FitViolationOut]


def _summary(fit: Fit) -> dict:
    return {
        "id": fit.pk,
        "ship_id": fit.ship_id,
        "ship_name": fit.ship.name,
        "name": fit.name,
        "status": fit.status,
        "dps": fit.dps,
        "volley": fit.volley,
        "ehp_k": fit.ehp_k,
        "speed_ms": fit.speed_ms,
        "sig_radius_m": fit.sig_radius_m,
        "cap_stable_pct": fit.cap_stable_pct,
        "cap_lasts_s": fit.cap_lasts_s,
        "targeting_range_km": fit.targeting_range_km,
        "stats_parse_ok": fit.stats_parse_ok,
        "has_links": fit.has_links,
        "unresolved_count": len(fit.unresolved_names or []),
        "created_by_id": fit.created_by_id,
        "created_by_name": fit.created_by.display_name if fit.created_by else "",
        "created_at": fit.created_at.isoformat(),
        "updated_at": fit.updated_at.isoformat(),
    }


def _can_edit(user: User, fit: Fit) -> bool:
    if permissions.can_manage_library(user):
        return True
    return fit.created_by_id == user.pk and fit.status == FitStatus.SUGGESTED


def _full(fit: Fit, user: User) -> dict:
    return {
        **_summary(fit),
        "eft_text": fit.eft_text,
        "pyfa_summary": fit.pyfa_summary,
        "unresolved_names": list(fit.unresolved_names or []),
        "reviewed_by_name": fit.reviewed_by.display_name if fit.reviewed_by else "",
        "reviewed_at": fit.reviewed_at.isoformat() if fit.reviewed_at else None,
        "can_edit": _can_edit(user, fit),
    }


def _queryset():
    return Fit.objects.select_related("ship", "created_by", "reviewed_by")


def _fit(fit_id: int) -> Fit:
    return get_object_or_404(_queryset(), pk=fit_id)


@router.get("", response=list[FitSummaryOut])
def list_fits(
    request: HttpRequest, ship: int | None = None, status: str | None = None, q: str | None = None
):
    permissions.require_browse_library(request.user)
    qs = _queryset()
    if ship is not None:
        qs = qs.filter(ship_id=ship)
    if status:
        qs = qs.filter(status__in=[s.strip() for s in status.split(",") if s.strip()])
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(ship__name__icontains=q))
    return [_summary(f) for f in qs]


@router.post("", response={201: FitOut})
def create_fit(request: HttpRequest, payload: FitCreateIn):
    permissions.require_browse_library(request.user)
    user = cast(User, request.user)
    try:
        fit = services.create_fit(
            user,
            eft_text=payload.eft_text,
            name=payload.name,
            pyfa_summary=payload.pyfa_summary,
            status=payload.status,
        )
    except services.FitError as exc:
        raise HttpError(exc.status, str(exc)) from exc
    return 201, _full(_fit(fit.pk), user)


@router.post("/parse", response=ParseOut)
def parse_fit(request: HttpRequest, payload: ParseIn):
    permissions.require_browse_library(request.user)
    pv = services.preview(payload.eft_text, payload.pyfa_summary)
    resolved, parsed = pv.resolved, pv.resolved.parsed
    items = []
    for r in resolved.items:
        t = r.type
        items.append(
            {
                "line_no": r.item.line_no,
                "name": r.item.name,
                "charge": r.item.charge,
                "quantity": r.item.quantity,
                "offline": r.item.offline,
                "type_id": t.pk if t else None,
                "group_name": t.group.name if t else None,
                "category_name": t.group.category.name if t else None,
                "meta_group_name": t.meta_group.name if t and t.meta_group else None,
                "meta_level": t.meta_level if t else None,
                "charge_type_id": r.charge_type.pk if r.charge_type else None,
            }
        )
    errors = list(parsed.errors)
    if parsed.ok and resolved.hull is None:
        errors.append(f"unknown hull {parsed.hull_name!r}")
    return {
        "ok": not errors,
        "hull_name": parsed.hull_name,
        "hull_type_id": resolved.hull.pk if resolved.hull else None,
        "fit_name": parsed.fit_name,
        "items": items,
        "unresolved": resolved.unresolved,
        "has_links": resolved.has_links,
        "stats": {**pv.stats.as_dict(), "ok": pv.stats.ok},
        "warnings": list(parsed.warnings),
        "errors": errors,
    }


@router.get("/{fit_id}", response=FitOut)
def get_fit(request: HttpRequest, fit_id: int):
    permissions.require_browse_library(request.user)
    return _full(_fit(fit_id), cast(User, request.user))


@router.patch("/{fit_id}", response=FitOut)
def patch_fit(request: HttpRequest, fit_id: int, payload: FitPatchIn):
    permissions.require_browse_library(request.user)
    user = cast(User, request.user)
    fit = _fit(fit_id)
    if not _can_edit(user, fit):
        raise HttpError(403, "you can only edit your own suggested fits")
    try:
        services.update_fit(
            user,
            fit,
            name=payload.name,
            eft_text=payload.eft_text,
            pyfa_summary=payload.pyfa_summary,
            status=payload.status,
            reason=payload.reason,
        )
    except services.FitError as exc:
        raise HttpError(exc.status, str(exc)) from exc
    return _full(_fit(fit.pk), user)


@router.get("/{fit_id}/legality", response=LegalityOut)
def fit_legality(request: HttpRequest, fit_id: int, ruleset: str, flagship: bool = False):
    permissions.require_browse_library(request.user)
    fit = _fit(fit_id)
    rs = get_object_or_404(Ruleset.objects.select_related("tournament"), tournament__code=ruleset)
    evaluation = services.evaluate_fit(fit, rs, is_flagship=flagship)
    return {
        "ruleset": rs.code,
        "revision": rs.revision,
        "is_flagship": flagship,
        "is_legal": evaluation.is_legal,
        "item_count": evaluation.item_count,
        "violations": [
            {
                "code": v.code,
                "severity": v.severity,
                "message": v.message,
                "line_nos": list(v.slot_nos),
                "data": dict(v.data),
            }
            for v in evaluation.violations
        ],
    }
