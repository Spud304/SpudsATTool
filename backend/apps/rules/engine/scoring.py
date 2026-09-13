"""Round scoring, entered after the fight: points destroyed, unspent handicap, differential."""

from . import codes
from .types import CompEvaluation, HullIndex, PointTable, RoundScore, RulesetSpec, SideScore


def _kill_points(
    evaluation: CompEvaluation,
    dead: frozenset[int],
    spec: RulesetSpec,
    kill_table: PointTable | None,
    hulls: HullIndex | None,
) -> int:
    total = 0
    for slot in evaluation.slots:
        if slot.slot_no not in dead:
            continue
        if spec.kill_points_source == codes.KILL_POINTS_KILL_TABLE and kill_table and hulls:
            hull = hulls.get(slot.type_id) if slot.type_id is not None else None
            if hull is not None:
                if hull.type_id in kill_table.hull_points:
                    total += kill_table.hull_points[hull.type_id]
                    continue
                if hull.ship_class is not None and hull.ship_class in kill_table.class_points:
                    total += kill_table.class_points[hull.ship_class]
                    continue
        total += slot.total_points
    return total


def _side(
    evaluation: CompEvaluation,
    dead: frozenset[int],
    spec: RulesetSpec,
    kill_table: PointTable | None,
    hulls: HullIndex | None,
) -> SideScore:
    fielded = evaluation.total_points
    unspent = max(spec.point_cap - fielded, 0)
    lost = _kill_points(evaluation, dead, spec, kill_table, hulls)
    # The sheet's U19 term: unspent points count as already lost. Clamped so an over-cap
    # comp never produces a negative handicap.
    handicap = unspent if spec.unspent_points_to_opponent and fielded > 0 else 0
    return SideScore(
        fielded_points=fielded,
        unspent_points=unspent,
        points_lost=lost,
        handicap_conceded=handicap,
        points_conceded=lost + handicap,
    )


def score_round(
    spec: RulesetSpec,
    us: CompEvaluation,
    opp: CompEvaluation,
    us_dead: frozenset[int],
    opp_dead: frozenset[int],
    kill_table: PointTable | None = None,
    hulls: HullIndex | None = None,
    us_potential_dps: float | None = None,
    opp_potential_dps: float | None = None,
) -> RoundScore:
    ours = _side(us, us_dead, spec, kill_table, hulls)
    theirs = _side(opp, opp_dead, spec, kill_table, hulls)
    differential = theirs.points_conceded - ours.points_conceded
    leader = "US" if differential > 0 else "OPP" if differential < 0 else "TIED"

    indicator = codes.INDICATOR_NONE
    threshold = spec.point_threshold
    if threshold is not None and threshold > 0:
        if differential >= threshold:
            indicator = codes.INDICATOR_WINNING_BIG
        elif differential <= -threshold:
            indicator = codes.INDICATOR_LOSING_BIG

    hint = None
    if (
        spec.tiebreak_rule == codes.TIEBREAK_POTENTIAL_DPS
        and us_potential_dps is not None
        and opp_potential_dps is not None
    ):
        hint = f"potential DPS at t=0: us {us_potential_dps:.0f} vs opp {opp_potential_dps:.0f}"

    return RoundScore(
        us=ours,
        opp=theirs,
        differential=differential,
        leader=leader,
        differential_indicator=indicator,
        tiebreak_hint=hint,
    )
