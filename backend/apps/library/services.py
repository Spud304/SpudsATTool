"""Fit library write path and derived data. Every mutation lands in the audit log."""

import hashlib
from dataclasses import dataclass, field

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.accounts import permissions
from apps.accounts.models import User
from apps.audit.services import record
from apps.rules import adapters
from apps.rules.engine import FitEvaluation, FitItemSpec, evaluate_fit_modules
from apps.rules.models import Ruleset
from apps.sde.constants import CATEGORY_SHIP, GROUP_COMMAND_BURST
from apps.sde.models import EveType
from apps.sde.resolve import resolve_names

from .eft import EftItem, ParsedEft, parse_eft
from .models import Fit, FitStatus
from .pyfa import PyfaStats, parse_pyfa_summary


class FitError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ResolvedItem:
    item: EftItem
    type: EveType | None
    charge_type: EveType | None = None


@dataclass
class ResolvedFit:
    parsed: ParsedEft
    hull: EveType | None
    items: list[ResolvedItem] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def has_links(self) -> bool:
        return any(
            r.type is not None and r.type.group_id == GROUP_COMMAND_BURST for r in self.items
        )


@dataclass
class Preview:
    resolved: ResolvedFit
    stats: PyfaStats


def _types():
    return EveType.objects.filter(published=True, removed=False).select_related(
        "group", "group__category", "meta_group"
    )


def resolve_hull(name: str) -> EveType | None:
    found, _ = resolve_names([name], _types().filter(group__category_id=CATEGORY_SHIP), "hull")
    return found.get(name)


def resolve_fit(parsed: ParsedEft) -> ResolvedFit:
    hull = resolve_hull(parsed.hull_name) if parsed.ok else None
    out = ResolvedFit(parsed=parsed, hull=hull)
    if not parsed.ok:
        return out
    found, _ = resolve_names(parsed.names, _types(), "item")
    seen_missing: set[str] = set()
    for item in parsed.items:
        type_ = found.get(item.name)
        charge = found.get(item.charge) if item.charge else None
        for name, resolved in ((item.name, type_), (item.charge, charge)):
            if name and resolved is None and name not in seen_missing:
                seen_missing.add(name)
                out.unresolved.append(name)
        out.items.append(ResolvedItem(item=item, type=type_, charge_type=charge))
    return out


def item_specs(resolved: ResolvedFit) -> tuple[FitItemSpec, ...]:
    specs: list[FitItemSpec] = []
    for r in resolved.items:
        specs.append(_spec(r.item.line_no, r.item.name, r.type, r.item.quantity, r.item.offline))
        if r.item.charge:
            specs.append(_spec(r.item.line_no, r.item.charge, r.charge_type, 1, False))
    return tuple(specs)


def _spec(
    line_no: int, name: str, type_: EveType | None, quantity: int, offline: bool
) -> FitItemSpec:
    if type_ is None:
        return FitItemSpec(
            line_no=line_no, name=name, type_id=None, quantity=quantity, offline=offline
        )
    return FitItemSpec(
        line_no=line_no,
        name=type_.name,
        type_id=type_.pk,
        category_id=type_.group.category_id,
        group_id=type_.group_id,
        meta_group_id=type_.meta_group_id,
        meta_level=type_.meta_level,
        quantity=quantity,
        offline=offline,
    )


def preview(eft_text: str, pyfa_summary: str = "") -> Preview:
    return Preview(
        resolved=resolve_fit(parse_eft(eft_text)), stats=parse_pyfa_summary(pyfa_summary)
    )


def _apply_derived(fit: Fit, resolved: ResolvedFit, stats: PyfaStats) -> None:
    fit.has_links = resolved.has_links
    fit.unresolved_names = resolved.unresolved
    for key, value in stats.as_dict().items():
        setattr(fit, key, value)
    fit.stats_parse_ok = stats.ok


def _eft_digest(text: str) -> str:
    return f"sha1:{hashlib.sha1(text.encode()).hexdigest()[:12]} ({len(text)} chars)"


def _snapshot(fit: Fit) -> dict:
    return {
        "ship": fit.ship.name,
        "name": fit.name,
        "status": fit.status,
        "eft": _eft_digest(fit.eft_text),
        "pyfa": bool(fit.pyfa_summary),
        "has_links": fit.has_links,
    }


SUGGESTED = "suggested"


def _check_status(
    actor: User,
    status: str | None,
    current: str | None,
    *,
    choices: type[models.TextChoices] = FitStatus,
    label: str = "fit",
) -> str:
    """Anyone may suggest; only library managers pick another status."""
    if status is None:
        return current or SUGGESTED
    if status not in choices.values:
        raise FitError(422, f"unknown {label} status {status!r}")
    if status != SUGGESTED and not permissions.can_manage_library(actor):
        raise FitError(403, f"only theorycrafters and above change {label} status")
    return status


def create_fit(
    actor: User,
    *,
    eft_text: str,
    name: str | None = None,
    pyfa_summary: str = "",
    status: str | None = None,
) -> Fit:
    parsed = parse_eft(eft_text)
    if not parsed.ok:
        raise FitError(422, "; ".join(parsed.errors))
    resolved = resolve_fit(parsed)
    if resolved.hull is None:
        raise FitError(422, f"unknown hull {parsed.hull_name!r}")
    final_status = _check_status(actor, status, None)
    fit = Fit(
        ship=resolved.hull,
        name=(name or parsed.fit_name).strip()[:120],
        status=final_status,
        eft_text=eft_text.replace("\r\n", "\n"),
        pyfa_summary=pyfa_summary,
        created_by=actor,
    )
    if final_status != FitStatus.SUGGESTED:
        fit.reviewed_by, fit.reviewed_at = actor, timezone.now()
    _apply_derived(fit, resolved, parse_pyfa_summary(pyfa_summary))
    try:
        with transaction.atomic():
            fit.save()
    except IntegrityError as exc:
        raise FitError(409, f"{fit.ship.name} already has a fit named {fit.name!r}") from exc
    record(actor=actor, action="fit.created", target=fit, after=_snapshot(fit))
    return fit


def update_fit(
    actor: User,
    fit: Fit,
    *,
    name: str | None = None,
    eft_text: str | None = None,
    pyfa_summary: str | None = None,
    status: str | None = None,
    reason: str = "",
) -> Fit:
    before = _snapshot(fit)
    if status is not None and status != fit.status:
        new_status = _check_status(actor, status, fit.status)
        fit.status = new_status
        fit.reviewed_by, fit.reviewed_at = actor, timezone.now()
        status_changed = True
    else:
        status_changed = False
    if name is not None:
        fit.name = name.strip()[:120]
    if pyfa_summary is not None:
        fit.pyfa_summary = pyfa_summary
    if eft_text is not None:
        parsed = parse_eft(eft_text)
        if not parsed.ok:
            raise FitError(422, "; ".join(parsed.errors))
        resolved = resolve_fit(parsed)
        if resolved.hull is None:
            raise FitError(422, f"unknown hull {parsed.hull_name!r}")
        if resolved.hull.pk != fit.ship_id:
            raise FitError(
                422,
                f"header hull {resolved.hull.name!r} does not match this fit's {fit.ship.name!r}",
            )
        fit.eft_text = eft_text.replace("\r\n", "\n")
    else:
        resolved = resolve_fit(parse_eft(fit.eft_text))
    _apply_derived(fit, resolved, parse_pyfa_summary(fit.pyfa_summary))
    try:
        with transaction.atomic():
            fit.save()
    except IntegrityError as exc:
        raise FitError(409, f"{fit.ship.name} already has a fit named {fit.name!r}") from exc
    after = _snapshot(fit)
    if status_changed:
        record(
            actor=actor,
            action="fit.status_changed",
            target=fit,
            reason=reason,
            before={"status": before["status"]},
            after={"status": after["status"]},
        )
    changed = {k: (before[k], after[k]) for k in before if before[k] != after[k] and k != "status"}
    if changed:
        record(
            actor=actor,
            action="fit.updated",
            target=fit,
            reason=reason,
            before={k: v[0] for k, v in changed.items()},
            after={k: v[1] for k, v in changed.items()},
        )
    return fit


def upsert_imported_fit(
    *, ship: EveType, name: str, status: str, eft_text: str, pyfa_summary: str
) -> tuple[Fit, bool, ResolvedFit]:
    """Workbook import path: no actor, no audit, keyed by (ship, name)."""
    resolved = resolve_fit(parse_eft(eft_text))
    fit, created = Fit.objects.get_or_create(
        ship=ship, name=name, defaults={"eft_text": eft_text, "status": status}
    )
    fit.status = status
    fit.eft_text = eft_text
    fit.pyfa_summary = pyfa_summary
    _apply_derived(fit, resolved, parse_pyfa_summary(pyfa_summary))
    fit.save()
    return fit, created, resolved


def evaluate_fit(fit: Fit, ruleset: Ruleset, *, is_flagship: bool = False) -> FitEvaluation:
    resolved = resolve_fit(parse_eft(fit.eft_text))
    return evaluate_fit_modules(
        item_specs(resolved), adapters.module_rules_for(ruleset), is_flagship=is_flagship
    )
