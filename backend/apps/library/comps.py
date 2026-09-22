"""Comp write path, evaluation and stat rollups. Fits stay in services.py."""

import hashlib
from dataclasses import dataclass
from statistics import mean

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import permissions
from apps.accounts.models import User
from apps.audit.services import record
from apps.rules import adapters, selection
from apps.rules.engine import BanInput, CompEvaluation, SlotInput, evaluate_comp
from apps.rules.models import Ruleset
from apps.sde.constants import CATEGORY_SHIP
from apps.sde.models import EveType

from .constants import LINK_SCRIPTS, MAX_LINK_SCRIPTS
from .models import Archetype, Comp, CompSlot, CompStatus, Fit
from .services import SUGGESTED, FitError, _check_status


class CompError(FitError):
    pass


class _Unset:
    pass


UNSET = _Unset()


@dataclass(frozen=True)
class SlotPatch:
    slot_no: int
    type_id: int | None = None
    is_flagship: bool = False
    is_unique: bool = False
    warp_in_km: int | None = None
    default_fit_id: int | None = None
    ship_note: str = ""
    link_scripts: tuple[str, ...] = ()


def queryset():
    return Comp.objects.select_related(
        "ruleset__tournament", "archetype", "created_by", "reviewed_by"
    ).prefetch_related("slots__ship", "slots__default_fit")


def slots_of(comp: Comp) -> list[CompSlot]:
    return list(comp.slots.all())


def _digest(text: str) -> str:
    return (
        f"sha1:{hashlib.sha1(text.encode()).hexdigest()[:12]} ({len(text)} chars)" if text else ""
    )


def _snapshot(comp: Comp) -> dict:
    return {
        "name": comp.name,
        "status": comp.status,
        "archetype": comp.archetype.name if comp.archetype else None,
        "notes": _digest(comp.notes),
        "ban_theory": _digest(comp.ban_theory),
    }


def _archetype(archetype_id: int | None) -> Archetype | None:
    if archetype_id is None:
        return None
    found = Archetype.objects.filter(pk=archetype_id).first()
    if found is None:
        raise CompError(422, f"unknown archetype {archetype_id}")
    return found


def _status(actor: User, status: str | None, current: str | None) -> str:
    try:
        return _check_status(actor, status, current, choices=CompStatus, label="comp")
    except FitError as exc:
        raise CompError(exc.status, str(exc)) from exc


def create_comp(
    actor: User,
    *,
    name: str,
    ruleset: Ruleset | None = None,
    status: str | None = None,
    archetype_id: int | None = None,
    notes: str = "",
    ban_theory: str = "",
) -> Comp:
    ruleset = ruleset or selection.active_ruleset()
    if ruleset is None:
        raise CompError(422, "no ruleset imported; import one before building comps")
    name = name.strip()[:120]
    if not name:
        raise CompError(422, "comp name is required")
    final_status = _status(actor, status, None)
    comp = Comp(
        ruleset=ruleset,
        name=name,
        status=final_status,
        archetype=_archetype(archetype_id),
        notes=notes,
        ban_theory=ban_theory,
        created_by=actor,
    )
    if final_status != SUGGESTED:
        comp.reviewed_by, comp.reviewed_at = actor, timezone.now()
    try:
        with transaction.atomic():
            comp.save()
            CompSlot.objects.bulk_create(
                CompSlot(comp=comp, slot_no=i) for i in range(1, ruleset.fielded_pilots + 1)
            )
    except IntegrityError as exc:
        raise CompError(409, f"{ruleset.code} already has a comp named {name!r}") from exc
    record(actor=actor, action="comp.created", target=comp, after=_snapshot(comp))
    return comp


def _validate_slots(comp: Comp, patches: list[SlotPatch]) -> list[int]:
    """Apply a full slot replacement to comp.slots in memory; returns the changed slot numbers."""
    n = comp.ruleset.fielded_pilots
    if sorted(p.slot_no for p in patches) != list(range(1, n + 1)):
        raise CompError(422, f"slots must be exactly 1..{n}, each once")
    type_ids = {p.type_id for p in patches if p.type_id is not None}
    ships = {
        t.pk: t
        for t in EveType.objects.filter(
            pk__in=type_ids, published=True, removed=False, group__category_id=CATEGORY_SHIP
        )
    }
    fit_ids = {p.default_fit_id for p in patches if p.default_fit_id is not None}
    fits = {f.pk: f for f in Fit.objects.filter(pk__in=fit_ids).select_related("ship")}
    existing = {s.slot_no: s for s in comp.slots.all()}
    changed: list[int] = []
    for p in sorted(patches, key=lambda p: p.slot_no):
        if p.type_id is not None and p.type_id not in ships:
            raise CompError(422, f"slot {p.slot_no}: unknown hull id {p.type_id}")
        fit = None
        if p.default_fit_id is not None:
            fit = fits.get(p.default_fit_id)
            if fit is None:
                raise CompError(422, f"slot {p.slot_no}: unknown fit id {p.default_fit_id}")
            if fit.ship_id != p.type_id:
                hull = ships[p.type_id].name if p.type_id in ships else "an empty slot"
                raise CompError(
                    422, f"slot {p.slot_no}: fit {fit.name!r} is for {fit.ship.name}, not {hull}"
                )
        codes = list(p.link_scripts)
        if len(codes) > MAX_LINK_SCRIPTS:
            raise CompError(422, f"slot {p.slot_no}: at most {MAX_LINK_SCRIPTS} link scripts")
        if len(set(codes)) != len(codes):
            raise CompError(422, f"slot {p.slot_no}: duplicate link script")
        unknown = [c for c in codes if c not in LINK_SCRIPTS]
        if unknown:
            raise CompError(422, f"slot {p.slot_no}: unknown link script {unknown[0]!r}")
        if p.warp_in_km is not None and not 0 <= p.warp_in_km <= 1000:
            raise CompError(422, f"slot {p.slot_no}: warp-in must be 0..1000 km")
        slot = existing.get(p.slot_no) or CompSlot(comp=comp, slot_no=p.slot_no)
        new = (
            p.type_id,
            p.is_flagship,
            p.is_unique,
            p.warp_in_km,
            p.default_fit_id,
            p.ship_note.strip()[:300],
            codes,
        )
        old = (
            slot.ship_id,
            slot.is_flagship,
            slot.is_unique,
            slot.warp_in_km,
            slot.default_fit_id,
            slot.ship_note,
            list(slot.link_scripts or []),
        )
        if new != old:
            changed.append(p.slot_no)
        slot.ship = ships[p.type_id] if p.type_id is not None else None
        slot.is_flagship = p.is_flagship
        slot.is_unique = p.is_unique
        slot.warp_in_km = p.warp_in_km
        slot.default_fit = fit
        slot.ship_note = new[5]
        slot.link_scripts = codes
        existing[p.slot_no] = slot
    for slot in existing.values():
        slot.save()
    return changed


def update_comp(
    actor: User,
    comp: Comp,
    *,
    name: str | None = None,
    status: str | None = None,
    archetype_id: int | None | _Unset = UNSET,
    notes: str | None = None,
    ban_theory: str | None = None,
    slots: list[SlotPatch] | None = None,
    clear_over_count: bool = False,
    reason: str = "",
) -> Comp:
    before = _snapshot(comp)
    status_changed = False
    if status is not None and status != comp.status:
        comp.status = _status(actor, status, comp.status)
        comp.reviewed_by, comp.reviewed_at = actor, timezone.now()
        status_changed = True
    if name is not None:
        comp.name = name.strip()[:120]
        if not comp.name:
            raise CompError(422, "comp name is required")
    if not isinstance(archetype_id, _Unset):
        comp.archetype = _archetype(archetype_id)
    if notes is not None:
        comp.notes = notes
    if ban_theory is not None:
        comp.ban_theory = ban_theory
    changed_slots: list[int] = []
    try:
        with transaction.atomic():
            comp.save()
            if slots is not None:
                changed_slots = _validate_slots(comp, slots)
            if clear_over_count:
                over = comp.slots.filter(slot_no__gt=comp.ruleset.fielded_pilots)
                changed_slots += list(over.values_list("slot_no", flat=True))
                over.delete()
    except IntegrityError as exc:
        raise CompError(409, f"{comp.ruleset.code} already has a comp named {comp.name!r}") from exc
    after = _snapshot(comp)
    if status_changed:
        record(
            actor=actor,
            action="comp.status_changed",
            target=comp,
            reason=reason,
            before={"status": before["status"]},
            after={"status": after["status"]},
        )
    diff = {k: (before[k], after[k]) for k in before if k != "status" and before[k] != after[k]}
    if diff or changed_slots:
        record(
            actor=actor,
            action="comp.updated",
            target=comp,
            reason=reason,
            before={k: v[0] for k, v in diff.items()},
            after={**{k: v[1] for k, v in diff.items()}, "slots_changed": changed_slots},
        )
    return comp


def clone_comp(
    actor: User,
    comp: Comp,
    *,
    name: str | None = None,
    ruleset: Ruleset | None = None,
    status: str | None = None,
) -> Comp:
    target = ruleset or comp.ruleset
    if status is None and permissions.can_manage_library(actor):
        status = comp.status  # managers keep the source status; everyone else lands in suggested
    new = create_comp(
        actor,
        name=name or f"{comp.name} (copy)",
        ruleset=target,
        status=status,
        archetype_id=comp.archetype_id,
        notes=comp.notes,
        ban_theory=comp.ban_theory,
    )
    source = {s.slot_no: s for s in comp.slots.all()}
    for slot in new.slots.all():
        src = source.get(slot.slot_no)
        if src is None:
            continue
        slot.ship_id = src.ship_id
        slot.is_flagship = src.is_flagship
        slot.is_unique = src.is_unique
        slot.warp_in_km = src.warp_in_km
        slot.default_fit_id = src.default_fit_id
        slot.ship_note = src.ship_note
        slot.link_scripts = list(src.link_scripts or [])
        slot.save()
    record(
        actor=actor,
        action="comp.cloned",
        target=new,
        after={"source_id": comp.pk, "source": comp.name, "ruleset": target.code},
    )
    return new


def slot_inputs(comp: Comp) -> list[SlotInput]:
    out = []
    for s in comp.slots.all():
        fit = s.default_fit
        has_links = fit.has_links if fit is not None else bool(s.link_scripts)
        out.append(
            SlotInput(
                slot_no=s.slot_no,
                type_id=s.ship_id,
                is_flagship=s.is_flagship,
                is_unique=s.is_unique,
                has_links=has_links,
            )
        )
    return out


def evaluate(comp: Comp, banned_type_ids: tuple[int, ...] = ()) -> CompEvaluation | None:
    try:
        inputs = adapters.engine_inputs_for(comp.ruleset)
    except adapters.NoPointTable:
        return None
    bans = [BanInput(type_id=t, ship_class=None, made_by_side="A") for t in banned_type_ids]
    return evaluate_comp(inputs.spec, inputs.table, inputs.hulls, slot_inputs(comp), bans)


def comp_stats(comp: Comp) -> dict:
    fits = [s.default_fit for s in comp.slots.all() if s.default_fit is not None]
    with_stats = [f for f in fits if f.stats_parse_ok]
    speeds = [f.speed_ms for f in with_stats if f.speed_ms is not None]
    return {
        "dps_total": sum(f.dps or 0 for f in with_stats) if with_stats else None,
        "ehp_k_total": sum(f.ehp_k or 0 for f in with_stats) if with_stats else None,
        "speed_avg": round(mean(speeds), 1) if speeds else None,
        "speed_min": min(speeds) if speeds else None,
        "fits_set": len(fits),
        "fits_with_stats": len(with_stats),
    }


def upsert_imported_comp(
    *,
    ruleset: Ruleset,
    name: str,
    status: str,
    notes: str,
    ban_theory: str,
    slots: list[SlotPatch],
) -> tuple[Comp, bool]:
    """Workbook import path: no actor, no audit; matches an existing comp by name, case-insensitively."""
    comp = Comp.objects.filter(ruleset=ruleset, name__iexact=name).first()
    created = comp is None
    if comp is None:
        comp = Comp(ruleset=ruleset, name=name)
    comp.status = status
    comp.notes = notes
    comp.ban_theory = ban_theory
    with transaction.atomic():
        comp.save()
        if created:
            CompSlot.objects.bulk_create(
                CompSlot(comp=comp, slot_no=i) for i in range(1, ruleset.fielded_pilots + 1)
            )
        _validate_slots(comp, slots)
    return comp, created


def create_archetype(actor: User, *, name: str, description: str = "", sort_order: int = 0):
    name = name.strip()[:60]
    if not name:
        raise CompError(422, "archetype name is required")
    try:
        with transaction.atomic():
            archetype = Archetype.objects.create(
                name=name, description=description, sort_order=sort_order
            )
    except IntegrityError as exc:
        raise CompError(409, f"archetype {name!r} exists") from exc
    record(actor=actor, action="archetype.created", target=archetype, after={"name": name})
    return archetype


def update_archetype(actor: User, archetype: Archetype, **fields) -> Archetype:
    before = {k: getattr(archetype, k) for k in fields}
    for key, value in fields.items():
        setattr(archetype, key, value.strip()[:60] if key == "name" else value)
    try:
        with transaction.atomic():
            archetype.save()
    except IntegrityError as exc:
        raise CompError(409, f"archetype {archetype.name!r} exists") from exc
    record(actor=actor, action="archetype.updated", target=archetype, before=before, after=fields)
    return archetype


def archetype_uses(archetype: Archetype) -> int:
    """Comps plus scrim sets (either side) that point at the archetype."""
    from apps.scrims.models import Set

    return (
        Comp.objects.filter(archetype=archetype).count()
        + Set.all_objects.filter(our_archetype=archetype).count()
        + Set.all_objects.filter(opp_archetype=archetype).count()
    )


def delete_archetype(actor: User, archetype: Archetype) -> None:
    uses = archetype_uses(archetype)
    if uses:
        raise CompError(409, f"{uses} comp(s) or set(s) use this archetype; retire it instead")
    record(actor=actor, action="archetype.deleted", target=archetype)
    archetype.delete()
