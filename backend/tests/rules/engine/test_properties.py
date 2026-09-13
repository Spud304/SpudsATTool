from collections import Counter
from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.rules.engine import SlotInput, evaluate_comp, score_round

from . import atxxii as at

hull_ids = st.sampled_from(sorted(at.HULLS))
modes = st.sampled_from(["per_copy_all", "escalating", "flat_additional"])


def comp(type_ids: list[int]) -> list[SlotInput]:
    return [SlotInput(i, t) for i, t in enumerate(type_ids, start=1)]


@settings(max_examples=200, deadline=None)
@given(st.lists(hull_ids, min_size=1, max_size=10), modes)
def test_total_is_sum_of_slots_and_evaluation_is_deterministic(type_ids, mode):
    spec = replace(at.SPEC, inflation_mode=mode)
    first = evaluate_comp(spec, at.TABLE, at.HULLS, comp(type_ids))
    second = evaluate_comp(spec, at.TABLE, at.HULLS, comp(type_ids))
    assert first == second
    assert first.total_points == sum(s.total_points for s in first.slots)


@settings(max_examples=200, deadline=None)
@given(st.lists(hull_ids, min_size=1, max_size=9), hull_ids, modes)
def test_adding_a_copy_never_lowers_an_existing_slot(type_ids, extra, mode):
    spec = replace(at.SPEC, inflation_mode=mode)
    before = evaluate_comp(spec, at.TABLE, at.HULLS, comp(type_ids))
    after = evaluate_comp(spec, at.TABLE, at.HULLS, comp(type_ids + [extra]))
    for old, new in zip(before.slots, after.slots, strict=False):
        assert new.total_points >= old.total_points


@settings(max_examples=150, deadline=None)
@given(st.permutations(list(at.OF99_SET1)))
def test_permuting_slots_preserves_total_and_violations(order):
    base = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, comp(list(at.OF99_SET1)))
    shuffled = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, comp(list(order)))
    assert shuffled.total_points == base.total_points == 200
    assert Counter(v.code for v in shuffled.violations) == Counter(v.code for v in base.violations)


@settings(max_examples=100, deadline=None)
@given(
    st.lists(hull_ids, min_size=10, max_size=10),
    st.lists(hull_ids, min_size=10, max_size=10),
    st.frozensets(st.integers(1, 10)),
    st.frozensets(st.integers(1, 10)),
)
def test_differential_is_antisymmetric(us_ids, opp_ids, us_dead, opp_dead):
    us = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, comp(us_ids))
    opp = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, comp(opp_ids))
    forward = score_round(at.SPEC, us, opp, us_dead, opp_dead)
    backward = score_round(at.SPEC, opp, us, opp_dead, us_dead)
    assert forward.differential == -backward.differential
