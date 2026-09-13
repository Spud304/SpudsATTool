from dataclasses import replace

from apps.rules.engine import (
    avalanche_allocation,
    ban_sequence,
    evaluate_comp,
    extra_bans_for_unique,
    flagship_uses_remaining,
    score_round,
)
from apps.rules.engine import codes as c
from apps.rules.engine.types import SlotInput

from . import atxxii as at


def full():
    return evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(*at.OF99_SET1))


class TestScoreRound:
    def test_no_deaths_no_handicap_is_tied(self):
        score = score_round(at.SPEC, full(), full(), frozenset(), frozenset())
        assert score.differential == 0 and score.leader == "TIED"
        assert score.us.handicap_conceded == 0

    def test_deaths_move_points_including_inflation(self):
        score = score_round(at.SPEC, full(), full(), frozenset({1}), frozenset({10}))
        assert score.us.points_lost == 36 and score.opp.points_lost == 7
        assert score.differential == 7 - 36 and score.leader == "OPP"

    def test_unspent_points_are_conceded(self):
        comp = list(at.OF99_SET1)
        comp[6] = at.RIFTER  # 191 points fielded
        under = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(*comp))
        score = score_round(at.SPEC, under, full(), frozenset(), frozenset())
        assert score.us.handicap_conceded == 9 and score.us.points_conceded == 9
        assert score.differential == -9
        no_handicap = replace(at.SPEC, unspent_points_to_opponent=False)
        assert score_round(no_handicap, under, full(), frozenset(), frozenset()).differential == 0

    def test_overcap_never_produces_negative_handicap(self):
        comp = list(at.OF99_SET1)
        comp[-1] = at.ASHIMMU
        over = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(*comp))
        assert (
            score_round(at.SPEC, over, full(), frozenset(), frozenset()).us.handicap_conceded == 0
        )

    def test_differential_indicator(self):
        spec = replace(at.SPEC, point_threshold=30)
        score = score_round(spec, full(), full(), frozenset(), frozenset({1, 2}))
        assert score.differential == 72 and score.differential_indicator == c.INDICATOR_WINNING_BIG
        score = score_round(spec, full(), full(), frozenset({1, 2}), frozenset())
        assert score.differential_indicator == c.INDICATOR_LOSING_BIG

    def test_tiebreak_hint(self):
        score = score_round(
            at.SPEC,
            full(),
            full(),
            frozenset(),
            frozenset(),
            us_potential_dps=8123.4,
            opp_potential_dps=7790,
        )
        assert score.tiebreak_hint == "potential DPS at t=0: us 8123 vs opp 7790"
        assert (
            score_round(
                at.AG7_SPEC,
                full(),
                full(),
                frozenset(),
                frozenset(),
                us_potential_dps=1,
                opp_potential_dps=2,
            ).tiebreak_hint
            is None
        )

    def test_kill_table_scoring(self):
        spec = replace(at.SPEC, kill_points_source="kill_table")
        kill = replace(
            at.TABLE,
            class_points={"Command Ship": 5, "Logistics Frigate": 1},
            hull_points={at.MAULUS: 9},
        )
        score = score_round(
            spec,
            full(),
            full(),
            frozenset({1, 8, 10}),
            frozenset(),
            kill_table=kill,
            hulls=at.HULLS,
        )
        assert score.us.points_lost == 5 + 1 + 9


class TestBans:
    def test_ban_sequences(self):
        assert ban_sequence(at.BRACKET, "A") == ("A", "B", "B", "A", "A", "B", "A", "B")
        assert ban_sequence(at.BRACKET, "B") == ("B", "A", "A", "B", "B", "A", "B", "A")
        assert ban_sequence(at.PRELIM, "A") == ("A", "B", "B", "A", "A", "B")
        assert ban_sequence(at.AG_STAGE, "A") == ("A", "B", "B", "A")
        assert ban_sequence(replace(at.PRELIM, bans_per_side=0, ban_order_pattern=""), "A") == ()

    def test_avalanche(self):
        assert avalanche_allocation(at.BRACKET, "A") == {"A": 1, "B": 2}
        assert avalanche_allocation(at.BRACKET, "B") == {"B": 1, "A": 2}
        assert avalanche_allocation(at.PRELIM, "A") == {"A": 0, "B": 0}

    def test_unique_extra_bans(self):
        assert extra_bans_for_unique([SlotInput(1, at.RATTLESNAKE, is_unique=True)], at.SPEC) == 2
        assert extra_bans_for_unique(at.slots(at.RATTLESNAKE), at.SPEC) == 0

    def test_flagship_uses(self):
        assert flagship_uses_remaining(at.BRACKET, 0, False, at.SPEC) == 1
        assert flagship_uses_remaining(at.BRACKET, 1, False, at.SPEC) == 0
        assert flagship_uses_remaining(at.BRACKET, 0, True, at.SPEC) == 0
        assert flagship_uses_remaining(at.AG_STAGE, 0, False, at.AG7_SPEC) == 0
