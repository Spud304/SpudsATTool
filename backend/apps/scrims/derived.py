"""Set documents: the stored rows plus everything the engine derives from them, built on every read.

Nothing derived is stored. One `evaluate_comp` per side per round and one `score_round` cost
microseconds, so the document is rebuilt for every response and every live event.
"""

from dataclasses import dataclass

from apps.rules import adapters
from apps.rules.engine import CompEvaluation, RoundScore
from apps.rules.engine.bans import ban_sequence, extra_bans_for_unique
from apps.rules.engine.codes import KILL_POINTS_KILL_TABLE, SIDE_A, SIDE_B
from apps.rules.engine.comp import evaluate_comp
from apps.rules.engine.scoring import score_round
from apps.rules.engine.types import BanInput, PointTable, SlotInput, StageSpec
from apps.rules.models import TablePurpose

from .models import Assignment, Ban, BanKind, LineupSide, Outcome, Round, Session, Set


@dataclass(frozen=True)
class Context:
    session: Session
    inputs: adapters.EngineInputs
    stage: StageSpec | None
    kill_table: PointTable | None

    @property
    def spec(self):
        return self.inputs.spec

    def hull_name(self, type_id: int | None) -> str | None:
        if type_id is None:
            return None
        hull = self.inputs.hulls.get(type_id)
        return hull.name if hull else None


def context_for(session: Session) -> Context:
    ruleset = session.ruleset
    inputs = adapters.engine_inputs_for(ruleset, session.point_table_version)
    stage = adapters.stage_spec(session.stage) if session.stage else None
    kill_table = None
    if inputs.spec.kill_points_source == KILL_POINTS_KILL_TABLE:
        version = ruleset.point_versions.filter(purpose=TablePurpose.KILL, is_current=True).first()
        if version is not None:
            kill_table = adapters.engine_inputs_for(ruleset, version).table
    return Context(session=session, inputs=inputs, stage=stage, kill_table=kill_table)


def other_side(side: str) -> str:
    return SIDE_B if side == SIDE_A else SIDE_A


# inputs


def slot_input(a: Assignment) -> SlotInput:
    return SlotInput(
        slot_no=a.slot_no,
        type_id=a.ship_id,
        is_flagship=a.is_flagship,
        is_unique=a.is_unique,
        has_links=a.fit.has_links if a.fit is not None else bool(a.link_scripts),
    )


def bans_in_effect(the_set: Set, round_no: int) -> list[Ban]:
    return [
        b
        for b in the_set.bans.all()
        if b.ship_id is not None and b.in_effect_from_round <= round_no
    ]


def _ban_inputs(bans: list[Ban]) -> list[BanInput]:
    return [
        BanInput(type_id=b.ship_id, ship_class=None, made_by_side=b.side, kind=b.kind) for b in bans
    ]


def evaluate_side(ctx: Context, assignments: list[Assignment], bans: list[Ban]) -> CompEvaluation:
    return evaluate_comp(
        ctx.spec,
        ctx.inputs.table,
        ctx.inputs.hulls,
        [slot_input(a) for a in assignments],
        _ban_inputs(bans),
    )


# documents


def _slot_doc(a: Assignment, evaluation: CompEvaluation, ctx: Context) -> dict:
    ev = next((s for s in evaluation.slots if s.slot_no == a.slot_no), None)
    return {
        "id": a.pk,
        "slot_no": a.slot_no,
        "pilot_id": a.pilot_id,
        "pilot_name": a.pilot.name if a.pilot else None,
        "pilot_user_id": a.pilot.user_id if a.pilot else None,
        "opp_pilot_name": a.opp_pilot_name,
        "type_id": a.ship_id,
        "ship_name": ctx.hull_name(a.ship_id) or (a.ship.name if a.ship else None),
        "hull_size": ev.effective_hull_size if ev else None,
        "is_flagship": a.is_flagship,
        "is_unique": a.is_unique,
        "warp_in_km": a.warp_in_km,
        "fit_id": a.fit_id,
        "fit_name": a.fit.name if a.fit else None,
        "fit_text": a.fit_text_snapshot,
        "load_default": a.load_default,
        "custom_note": a.custom_note,
        "repeat_note": a.repeat_note,
        "link_scripts": list(a.link_scripts or []),
        "died": a.died,
        "has_links": ev.has_links if ev else False,
        "base_points": ev.base_points if ev else 0,
        "inflation_points": ev.inflation_points if ev else 0,
        "total_points": ev.total_points if ev else 0,
        "is_banned": ev.is_banned if ev else False,
        "link_index": ev.link_index if ev else None,
        "flags": list(ev.flags) if ev else [],
    }


DUPLICATE_PILOT = "DUPLICATE_PILOT"


def _duplicate_pilots(assignments: list[Assignment]) -> list[dict]:
    """One pilot in two of our slots is a lineup mistake the engine cannot see; flag it as an error."""
    slots_by_pilot: dict[int, list[int]] = {}
    for a in assignments:
        if a.pilot_id is not None:
            slots_by_pilot.setdefault(a.pilot_id, []).append(a.slot_no)
    out = []
    for a in assignments:
        slots = slots_by_pilot.get(a.pilot_id or -1, [])
        if len(slots) > 1 and slots[0] == a.slot_no:
            out.append(
                {
                    "code": DUPLICATE_PILOT,
                    "severity": "error",
                    "message": f"{a.pilot.name if a.pilot else 'pilot'} is in slots "
                    + " and ".join(str(n) for n in slots),
                    "slot_nos": slots,
                    "data": {"pilot_id": a.pilot_id or 0},
                }
            )
    return out


def _side_doc(assignments: list[Assignment], evaluation: CompEvaluation, ctx: Context) -> dict:
    dead = {a.slot_no for a in assignments if a.died}
    duplicates = _duplicate_pilots(assignments)
    flagged = {n for v in duplicates for n in v["slot_nos"]}
    slots = [_slot_doc(a, evaluation, ctx) for a in assignments]
    for slot in slots:
        if slot["slot_no"] in flagged:
            slot["flags"] = [*slot["flags"], DUPLICATE_PILOT]
    return {
        "slots": slots,
        "total_points": evaluation.total_points,
        "point_cap": evaluation.point_cap,
        "cap_status": evaluation.cap_status,
        "unspent_points": evaluation.unspent_points,
        "is_legal": evaluation.is_legal and not duplicates,
        "violations": [
            {
                "code": v.code,
                "severity": v.severity,
                "message": v.message,
                "slot_nos": list(v.slot_nos),
                "data": dict(v.data),
            }
            for v in evaluation.violations
        ]
        + duplicates,
        "points_lost": sum(s.total_points for s in evaluation.slots if s.slot_no in dead),
        "dead_count": len(dead),
    }


def _score_doc(score: RoundScore) -> dict:
    def side(s):
        return {
            "fielded_points": s.fielded_points,
            "unspent_points": s.unspent_points,
            "points_lost": s.points_lost,
            "handicap_conceded": s.handicap_conceded,
            "points_conceded": s.points_conceded,
        }

    return {
        "us": side(score.us),
        "opp": side(score.opp),
        "differential": score.differential,
        "leader": score.leader,
        "indicator": score.differential_indicator,
        "point_threshold": None,
    }


def round_document(ctx: Context, the_set: Set, rnd: Round) -> dict:
    rows = list(rnd.assignments.all())
    us = sorted((a for a in rows if a.side == LineupSide.US), key=lambda a: a.slot_no)
    opp = sorted((a for a in rows if a.side == LineupSide.OPP), key=lambda a: a.slot_no)
    bans = bans_in_effect(the_set, rnd.round_no)
    us_eval = evaluate_side(ctx, us, bans)
    opp_eval = evaluate_side(ctx, opp, bans)
    score = score_round(
        ctx.spec,
        us_eval,
        opp_eval,
        frozenset(a.slot_no for a in us if a.died),
        frozenset(a.slot_no for a in opp if a.died),
        kill_table=ctx.kill_table,
        hulls=ctx.inputs.hulls,
    )
    score_doc = _score_doc(score)
    score_doc["point_threshold"] = ctx.spec.point_threshold
    return {
        "id": rnd.pk,
        "round_no": rnd.round_no,
        "outcome": rnd.outcome,
        "notes": rnd.notes,
        "banned_type_ids": sorted({b.ship_id for b in bans if b.ship_id is not None}),
        "us": _side_doc(us, us_eval, ctx),
        "opp": _side_doc(opp, opp_eval, ctx),
        "score": score_doc,
    }


def _ban_chip(b: Ban, the_set: Set, ctx: Context, order: int | None) -> dict:
    return {
        "id": b.pk,
        "order": order,
        "side": b.side,
        "is_ours": b.side == the_set.our_side,
        "kind": b.kind,
        "index": b.index,
        "type_id": b.ship_id,
        "ship_name": ctx.hull_name(b.ship_id) or (b.ship.name if b.ship else None),
        "in_effect_from_round": b.in_effect_from_round,
    }


def _standard_chips(ctx: Context, the_set: Set) -> list[dict]:
    """Standard bans laid out in the stage's pick order, so the board reads left to right."""
    rows = {(b.side, b.index): b for b in the_set.bans.all() if b.kind == BanKind.STANDARD}
    if ctx.stage is None or not ctx.stage.ban_order_pattern:
        return [_ban_chip(b, the_set, ctx, None) for (_, _), b in sorted(rows.items())]
    chips = []
    counts = {SIDE_A: 0, SIDE_B: 0}
    for order, side in enumerate(ban_sequence(ctx.stage, SIDE_A), start=1):
        counts[side] += 1
        ban = rows.get((side, counts[side]))
        if ban is None:
            chips.append(
                {
                    "id": None,
                    "order": order,
                    "side": side,
                    "is_ours": side == the_set.our_side,
                    "kind": BanKind.STANDARD,
                    "index": counts[side],
                    "type_id": None,
                    "ship_name": None,
                    "in_effect_from_round": 1,
                }
            )
        else:
            chips.append(_ban_chip(ban, the_set, ctx, order))
    return chips


def set_document(ctx: Context, the_set: Set) -> dict:
    rounds = [round_document(ctx, the_set, r) for r in the_set.rounds.all()]
    first_us = rounds[0]["us"]["slots"] if rounds else []
    extra = extra_bans_for_unique(
        [
            SlotInput(slot_no=s["slot_no"], type_id=s["type_id"], is_unique=s["is_unique"])
            for s in first_us
        ],
        ctx.spec,
    )
    outcomes = [r["outcome"] for r in rounds]
    avalanche = sorted(
        (b for b in the_set.bans.all() if b.kind != BanKind.STANDARD),
        key=lambda b: (b.in_effect_from_round, b.kind, b.side, b.index),
    )
    return {
        "id": the_set.pk,
        "index": the_set.index,
        "label": the_set.label,
        "comp_id": the_set.comp_id,
        "comp_name": the_set.comp.name if the_set.comp else None,
        "our_archetype_id": the_set.our_archetype_id,
        "opp_archetype_id": the_set.opp_archetype_id,
        "our_side": the_set.our_side,
        "tactics_note": the_set.tactics_note,
        "link_note": the_set.link_note,
        "warp_calls": list(the_set.warp_calls or []),
        "bans": _standard_chips(ctx, the_set),
        "avalanche_bans": [_ban_chip(b, the_set, ctx, None) for b in avalanche],
        "bans_per_side": ctx.stage.bans_per_side if ctx.stage else 0,
        "bans_are_blind": ctx.stage.bans_are_blind if ctx.stage else False,
        "avalanche_enabled": ctx.stage.avalanche_enabled if ctx.stage else False,
        "extra_bans_owed": extra,
        "rounds": rounds,
        "record": {
            "wins": outcomes.count(Outcome.WIN),
            "losses": outcomes.count(Outcome.LOSS),
            "draws": outcomes.count(Outcome.DRAW),
        },
    }


SET_PREFETCH = (
    "bans__ship",
    "comp",
    "rounds__assignments__pilot__user",
    "rounds__assignments__ship",
    "rounds__assignments__fit",
)


def load_set(set_id: int) -> Set:
    return (
        Set.objects.select_related("session__ruleset", "session__stage", "comp")
        .prefetch_related(*SET_PREFETCH)
        .get(pk=set_id)
    )
