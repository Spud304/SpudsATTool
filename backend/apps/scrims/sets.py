"""Sets, bans, rounds and lineups. Every function here runs under the session lock and emits one event."""

from typing import Any

from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record
from apps.library.constants import LINK_SCRIPTS
from apps.library.models import Comp, CompSlot, Fit
from apps.rules.engine.bans import avalanche_allocation
from apps.rules.engine.codes import SIDE_A

from . import derived, events
from .constants import WARP_CALLS_PER_SET
from .models import (
    Assignment,
    Ban,
    BanKind,
    LineupSide,
    Outcome,
    Pilot,
    Round,
    Session,
    Set,
    Side,
)
from .roster import ScrimError
from .sessions import scope

_UNSET = object()

PILOT_OWN_FIELDS = frozenset({"fit_id", "custom_note", "warp_in_km"})


def _check(value: str, choices, label: str) -> str:
    if value not in choices.values:
        raise ScrimError(422, f"unknown {label} {value!r}")
    return value


def _emit_set(session: Session, the_set: Set, actor) -> dict:
    fresh = derived.load_set(the_set.pk)
    doc = derived.set_document(derived.context_for(session), fresh)
    events.emit(session, events.KIND_SET, {"set": doc}, actor)
    return doc


def _hull_or_422(ctx: derived.Context, type_id: int | None) -> int | None:
    if type_id is None:
        return None
    if ctx.inputs.hulls.get(type_id) is None:
        raise ScrimError(422, f"type {type_id} is not a hull in {ctx.session.ruleset.code}")
    return type_id


# sets


def _blank_assignments(rnd: Round, fielded: int) -> list[Assignment]:
    return [
        Assignment(round=rnd, side=side, slot_no=n)
        for side in (LineupSide.US, LineupSide.OPP)
        for n in range(1, fielded + 1)
    ]


def _copy_assignments(source: Round, target: Round) -> list[Assignment]:
    rows = []
    for a in source.assignments.all():
        rows.append(
            Assignment(
                round=target,
                side=a.side,
                slot_no=a.slot_no,
                pilot_id=a.pilot_id,
                opp_pilot_name=a.opp_pilot_name,
                ship_id=a.ship_id,
                is_flagship=a.is_flagship,
                is_unique=a.is_unique,
                warp_in_km=a.warp_in_km,
                fit_id=a.fit_id,
                fit_text_snapshot=a.fit_text_snapshot,
                load_default=a.load_default,
                custom_note=a.custom_note,
                repeat_note=a.repeat_note,
                link_scripts=list(a.link_scripts or []),
                died=False,
            )
        )
    return rows


def create_set(
    actor: User, session_id: int, *, copy_previous: bool = True, label: str = ""
) -> dict:
    with events.locked(session_id) as session:
        if session.is_archived:
            raise ScrimError(409, "this scrim is archived")
        ctx = derived.context_for(session)
        previous = session.sets.order_by("-index").first()
        our_side = session.default_our_side or (previous.our_side if previous else SIDE_A)
        index = (previous.index + 1) if previous else 1
        # A soft-deleted set holding this index loses its restore window to the new set.
        Set.all_objects.filter(session=session, index=index, deleted_at__isnull=False).delete()
        the_set = Set.objects.create(
            session=session,
            index=index,
            label=label.strip()[:60],
            our_side=our_side,
            comp=previous.comp if (previous and copy_previous) else None,
            our_archetype=previous.our_archetype if (previous and copy_previous) else None,
            opp_archetype=previous.opp_archetype if (previous and copy_previous) else None,
            warp_calls=list(previous.warp_calls) if (previous and copy_previous) else [],
        )
        per_side = ctx.stage.bans_per_side if ctx.stage else 0
        Ban.objects.bulk_create(
            Ban(set=the_set, side=side, kind=BanKind.STANDARD, index=i)
            for side in (Side.A, Side.B)
            for i in range(1, per_side + 1)
        )
        rnd = Round.objects.create(set=the_set, round_no=1)
        source = (
            previous.rounds.order_by("-round_no").first() if (previous and copy_previous) else None
        )
        if source is not None:
            Assignment.objects.bulk_create(_copy_assignments(source, rnd))
        else:
            Assignment.objects.bulk_create(_blank_assignments(rnd, ctx.spec.fielded_pilots))
        record(
            actor=actor,
            scope=scope(session),
            action="set.created",
            target=the_set,
            target_label=f"{session.title} set {the_set.index}",
        )
        return _emit_set(session, the_set, actor)


def _set_in(session: Session, set_id: int) -> Set:
    the_set = session.sets.filter(pk=set_id).first()
    if the_set is None:
        raise ScrimError(404, "no such set in this scrim")
    return the_set


def delete_set(actor: User, session_id: int, set_id: int, reason: str = "") -> None:
    """Soft delete: the set drops out of every read and can be restored from the history drawer."""
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        the_set.deleted_at = timezone.now()
        the_set.deleted_by = actor
        the_set.save(update_fields=["deleted_at", "deleted_by"])
        record(
            actor=actor,
            scope=scope(session),
            action="set.deleted",
            target_type="scrims.set",
            target_id=str(set_id),
            target_label=f"{session.title} set {the_set.index}",
            reason=reason,
        )
        events.emit(session, events.KIND_SET_DELETED, {"set_id": set_id}, actor)


def restore_set(actor: User, session_id: int, set_id: int) -> dict:
    with events.locked(session_id) as session:
        the_set = Set.all_objects.filter(
            session=session, pk=set_id, deleted_at__isnull=False
        ).first()
        if the_set is None:
            raise ScrimError(404, "no deleted set with that id on this scrim")
        the_set.deleted_at = None
        the_set.deleted_by = None
        the_set.save(update_fields=["deleted_at", "deleted_by"])
        record(
            actor=actor,
            scope=scope(session),
            action="set.restored",
            target=the_set,
            target_label=f"{session.title} set {the_set.index}",
        )
        return _emit_set(session, the_set, actor)


def _warp_calls(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > WARP_CALLS_PER_SET:
        raise ScrimError(422, f"warp_calls must be a list of up to {WARP_CALLS_PER_SET} labels")
    return [str(v).strip()[:40] for v in value]


def patch_set(actor: User, session_id: int, set_id: int, **fields) -> dict:
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        if "label" in fields:
            the_set.label = (fields["label"] or "").strip()[:60]
        if "our_side" in fields:
            the_set.our_side = _check(fields["our_side"], Side, "side")
        if "tactics_note" in fields:
            the_set.tactics_note = fields["tactics_note"] or ""
        if "link_note" in fields:
            the_set.link_note = (fields["link_note"] or "")[:300]
        if "warp_calls" in fields:
            the_set.warp_calls = _warp_calls(fields["warp_calls"])
        for key in ("our_archetype_id", "opp_archetype_id"):
            if key in fields:
                setattr(the_set, key, fields[key])
        the_set.save()
        if "comp_id" in fields:
            _load_comp(session, the_set, fields["comp_id"])
        return _emit_set(session, the_set, actor)


# comp load and the override rule


def _apply_defaults(a: Assignment, slot: CompSlot) -> None:
    fit = slot.default_fit
    a.ship_id = slot.ship_id
    a.is_flagship = slot.is_flagship
    a.is_unique = slot.is_unique
    a.warp_in_km = slot.warp_in_km
    a.fit = fit
    a.fit_text_snapshot = fit.eft_text if fit else ""
    a.repeat_note = slot.ship_note
    a.link_scripts = list(slot.link_scripts or [])
    a.load_default = True


def _clear_defaults(a: Assignment) -> None:
    a.fit = None
    a.fit_text_snapshot = ""
    a.repeat_note = ""
    a.link_scripts = []
    a.load_default = False


def _load_comp(session: Session, the_set: Set, comp_id: int | None) -> None:
    if comp_id is None:
        the_set.comp = None
        the_set.save(update_fields=["comp"])
        return
    comp = (
        Comp.objects.filter(pk=comp_id)
        .select_related("archetype")
        .prefetch_related("slots__default_fit")
        .first()
    )
    if comp is None:
        raise ScrimError(422, f"unknown comp {comp_id}")
    if comp.ruleset_id != session.ruleset_id:
        raise ScrimError(
            422, f"{comp.name} belongs to {comp.ruleset.code}, not {session.ruleset.code}"
        )
    slots = {s.slot_no: s for s in comp.slots.all()}
    the_set.comp = comp
    if the_set.our_archetype_id is None and comp.archetype_id is not None:
        the_set.our_archetype_id = comp.archetype_id
    the_set.save(update_fields=["comp", "our_archetype"])
    for rnd in the_set.rounds.all():
        for a in rnd.assignments.filter(side=LineupSide.US):
            slot = slots.get(a.slot_no)
            if slot is None or not a.load_default:
                continue
            _apply_defaults(a, slot)
            a.save()


# bans


def put_ban(
    actor: User,
    session_id: int,
    set_id: int,
    *,
    side: str,
    kind: str,
    index: int,
    type_id: int | None,
    in_effect_from_round: int = 1,
) -> dict:
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        ctx = derived.context_for(session)
        _check(side, Side, "side")
        _check(kind, BanKind, "ban kind")
        if index < 1:
            raise ScrimError(422, "ban index starts at 1")
        if kind == BanKind.STANDARD and ctx.stage and index > ctx.stage.bans_per_side:
            raise ScrimError(422, f"this stage allows {ctx.stage.bans_per_side} bans per side")
        _hull_or_422(ctx, type_id)
        ban, _ = Ban.objects.get_or_create(
            set=the_set,
            side=side,
            kind=kind,
            index=index,
            defaults={"in_effect_from_round": in_effect_from_round},
        )
        ban.ship_id = type_id
        ban.in_effect_from_round = 1 if kind == BanKind.STANDARD else max(in_effect_from_round, 1)
        ban.save()
        return _emit_set(session, the_set, actor)


def _ensure_avalanche_rows(ctx: derived.Context, the_set: Set, rnd: Round) -> None:
    """After a decided round, pre-create the empty avalanche chips the stage allows for the next round."""
    if ctx.stage is None or not ctx.stage.avalanche_enabled:
        return
    from_round = rnd.round_no + 1
    # Only empty rows are disposable: a recorded hull stays even if the outcome flips.
    the_set.bans.filter(
        kind=BanKind.AVALANCHE, in_effect_from_round=from_round, ship__isnull=True
    ).delete()
    if rnd.outcome not in (Outcome.WIN, Outcome.LOSS):
        return
    winner = (
        the_set.our_side if rnd.outcome == Outcome.WIN else derived.other_side(the_set.our_side)
    )
    for side, wanted in avalanche_allocation(ctx.stage, winner).items():
        have = the_set.bans.filter(
            kind=BanKind.AVALANCHE, side=side, in_effect_from_round=from_round
        ).count()
        taken = set(
            the_set.bans.filter(kind=BanKind.AVALANCHE, side=side).values_list("index", flat=True)
        )
        next_index = (max(taken) + 1) if taken else 1
        for _ in range(max(wanted - have, 0)):
            Ban.objects.create(
                set=the_set,
                side=side,
                kind=BanKind.AVALANCHE,
                index=next_index,
                in_effect_from_round=from_round,
            )
            next_index += 1


# rounds


def _round_in(the_set: Set, round_no: int) -> Round:
    rnd = the_set.rounds.filter(round_no=round_no).first()
    if rnd is None:
        raise ScrimError(404, f"set has no round {round_no}")
    return rnd


def add_round(actor: User, session_id: int, set_id: int) -> dict:
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        last = the_set.rounds.order_by("-round_no").first()
        round_no = (last.round_no + 1) if last else 1
        Round.all_objects.filter(set=the_set, round_no=round_no, deleted_at__isnull=False).delete()
        rnd = Round.objects.create(set=the_set, round_no=round_no)
        if last is not None:
            Assignment.objects.bulk_create(_copy_assignments(last, rnd))
        else:
            Assignment.objects.bulk_create(
                _blank_assignments(rnd, derived.context_for(session).spec.fielded_pilots)
            )
        return _emit_set(session, the_set, actor)


def delete_round(actor: User, session_id: int, set_id: int, round_no: int) -> dict:
    """Soft delete of the last round; restore from the history drawer while no newer round exists."""
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        rnd = _round_in(the_set, round_no)
        last = the_set.rounds.order_by("-round_no").first()
        if last is None or last.pk != rnd.pk:
            raise ScrimError(409, "only the last round can be removed")
        if round_no == 1:
            raise ScrimError(409, "a set keeps its first round; delete the set instead")
        rnd.deleted_at = timezone.now()
        rnd.deleted_by = actor
        rnd.save(update_fields=["deleted_at", "deleted_by"])
        the_set.bans.filter(
            kind=BanKind.AVALANCHE, in_effect_from_round__gt=round_no, ship__isnull=True
        ).delete()
        record(
            actor=actor,
            scope=scope(session),
            action="round.deleted",
            target=rnd,
            target_label=f"{session.title} set {the_set.index} R{round_no}",
        )
        return _emit_set(session, the_set, actor)


def round_restorable(the_set: Set, rnd: Round) -> bool:
    """A deleted round comes back only while nothing newer is live: later rounds copy from it."""
    return not the_set.rounds.filter(round_no__gt=rnd.round_no).exists()


def restore_round(actor: User, session_id: int, set_id: int, round_no: int) -> dict:
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        rnd = Round.all_objects.filter(
            set=the_set, round_no=round_no, deleted_at__isnull=False
        ).first()
        if rnd is None:
            raise ScrimError(404, f"set has no deleted round {round_no}")
        if not round_restorable(the_set, rnd):
            raise ScrimError(409, "a newer round exists; remove it before restoring this one")
        rnd.deleted_at = None
        rnd.deleted_by = None
        rnd.save(update_fields=["deleted_at", "deleted_by"])
        record(
            actor=actor,
            scope=scope(session),
            action="round.restored",
            target=rnd,
            target_label=f"{session.title} set {the_set.index} R{round_no}",
        )
        return _emit_set(session, the_set, actor)


def patch_round(
    actor: User,
    session_id: int,
    set_id: int,
    round_no: int,
    *,
    outcome: Any = _UNSET,
    notes: Any = _UNSET,
) -> dict:
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        rnd = _round_in(the_set, round_no)
        ctx = derived.context_for(session)
        if outcome is not _UNSET:
            rnd.outcome = _check(outcome, Outcome, "outcome")
        if notes is not _UNSET:
            rnd.notes = notes or ""
        rnd.save()
        if outcome is not _UNSET:
            _ensure_avalanche_rows(ctx, the_set, rnd)
        return _emit_set(session, the_set, actor)


# assignments


def _assignment(the_set: Set, round_no: int, side: str, slot_no: int) -> Assignment:
    _check(side, LineupSide, "lineup side")
    rnd = _round_in(the_set, round_no)
    a = rnd.assignments.select_related("fit", "pilot").filter(side=side, slot_no=slot_no).first()
    if a is None:
        raise ScrimError(404, f"no slot {slot_no} on side {side}")
    return a


def _link_scripts(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 5:
        raise ScrimError(422, "link_scripts is a list of up to five script codes")
    bad = [v for v in value if v not in LINK_SCRIPTS]
    if bad:
        raise ScrimError(422, f"unknown link script {bad[0]!r}")
    return list(value)


def patch_assignment(
    actor: User, session_id: int, set_id: int, round_no: int, side: str, slot_no: int, **fields
) -> dict:
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        ctx = derived.context_for(session)
        a = _assignment(the_set, round_no, side, slot_no)
        comp_slot = None
        if the_set.comp_id is not None and side == LineupSide.US:
            comp_slot = (
                CompSlot.objects.select_related("default_fit")
                .filter(comp_id=the_set.comp_id, slot_no=slot_no)
                .first()
            )

        if "type_id" in fields:
            new_ship = _hull_or_422(ctx, fields["type_id"])
            if new_ship != a.ship_id:
                a.ship_id = new_ship
                if comp_slot is not None and new_ship != comp_slot.ship_id:
                    _clear_defaults(
                        a
                    )  # the override rule: a different hull drops the comp's defaults
                elif a.fit is not None and a.fit.ship_id != new_ship:
                    a.fit = None
                    a.fit_text_snapshot = ""
        if fields.get("load_default") is True and comp_slot is not None:
            _apply_defaults(a, comp_slot)
        elif "load_default" in fields:
            a.load_default = bool(fields["load_default"])
        if "fit_id" in fields:
            fit_id = fields["fit_id"]
            if fit_id is None:
                a.fit = None
                a.fit_text_snapshot = ""
            else:
                fit = Fit.objects.filter(pk=fit_id).first()
                if fit is None:
                    raise ScrimError(422, f"unknown fit {fit_id}")
                if a.ship_id is not None and fit.ship_id != a.ship_id:
                    raise ScrimError(
                        422, f"{fit.name} is a {fit.ship.name} fit, not for this slot's hull"
                    )
                if a.ship_id is None:
                    a.ship_id = _hull_or_422(ctx, fit.ship_id)
                a.fit = fit
                a.fit_text_snapshot = fit.eft_text
        if "pilot_id" in fields:
            if side != LineupSide.US:
                raise ScrimError(422, "only our slots take a pilot")
            pilot_id = fields["pilot_id"]
            if pilot_id is not None and not Pilot.objects.filter(pk=pilot_id).exists():
                raise ScrimError(422, f"unknown pilot {pilot_id}")
            a.pilot_id = pilot_id
        if "opp_pilot_name" in fields:
            a.opp_pilot_name = (fields["opp_pilot_name"] or "")[:100]
        for key in ("is_flagship", "is_unique", "died"):
            if key in fields:
                setattr(a, key, bool(fields[key]))
        if "warp_in_km" in fields:
            a.warp_in_km = fields["warp_in_km"]
        if "custom_note" in fields:
            a.custom_note = (fields["custom_note"] or "")[:300]
        if "link_scripts" in fields:
            a.link_scripts = _link_scripts(fields["link_scripts"])
        a.save()
        return _emit_set(session, the_set, actor)


def paste_opp_lineup(
    actor: User, session_id: int, set_id: int, round_no: int, text: str
) -> tuple[dict, list[str]]:
    """Ten hull names from chat, one per line (or comma separated), into the opponent's slots in order."""
    with events.locked(session_id) as session:
        the_set = _set_in(session, set_id)
        ctx = derived.context_for(session)
        rnd = _round_in(the_set, round_no)
        by_name = {h.name.lower(): h.type_id for h in ctx.inputs.hulls.values()}
        names = [n.strip() for chunk in text.splitlines() for n in chunk.split(",") if n.strip()]
        slots = list(rnd.assignments.filter(side=LineupSide.OPP).order_by("slot_no"))
        unresolved: list[str] = []
        for a, name in zip(slots, names, strict=False):
            type_id = by_name.get(name.lower())
            if type_id is None:
                unresolved.append(name)
                continue
            a.ship_id = type_id
            a.save(update_fields=["ship"])
        for a in slots[len(names) :]:
            if a.ship_id is not None:
                a.ship_id = None
                a.save(update_fields=["ship"])
        if len(names) > len(slots):
            unresolved.extend(names[len(slots) :])
        return _emit_set(session, the_set, actor), unresolved
