import json
from dataclasses import replace
from pathlib import Path

from apps.rules.engine import BanInput, SlotInput, evaluate_comp, inflation_points
from apps.rules.engine import codes as c

from . import atxxii as at

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def codes_of(evaluation) -> set[str]:
    return {v.code for v in evaluation.violations}


def errors_of(evaluation) -> set[str]:
    return {v.code for v in evaluation.violations if v.severity == c.SEVERITY_ERROR}


class TestOf99Set1:
    """The golden comp from the OF 99 practice sheet: exactly 200 under per_copy_all."""

    def test_matches_the_sheet(self):
        golden = json.loads((FIXTURES / "of99_set1.json").read_text(encoding="utf-8"))
        result = evaluate_comp(
            at.SPEC, at.TABLE, at.HULLS, at.slots(*at.OF99_SET1, links_at=(1, 2, 3))
        )
        assert result.total_points == golden["expected"]["total_points"] == 200
        assert result.cap_status == c.CAP_EXACT and result.is_legal
        by_slot = {s.slot_no: s for s in result.slots}
        for expected in golden["expected"]["slots"]:
            slot = by_slot[expected["slot_no"]]
            assert slot.name == expected["name"]
            assert slot.total_points == expected["total_points"], slot
            assert slot.inflation_points == expected["inflation_points"], slot
        assert [s.link_index for s in result.slots[:3]] == [1, 2, 3]
        assert all(s.link_index is None for s in result.slots[3:])
        assert errors_of(result) == set()

    def test_deacons_pay_the_lf_surcharge_and_keres_does_not(self):
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(*at.OF99_SET1))
        by_name = {s.name: s for s in result.slots}
        assert by_name["Deacon"].total_points == 11 and by_name["Deacon"].copies_of_hull == 2
        assert by_name["Keres"].total_points == 12 and by_name["Keres"].inflation_points == 0


class TestInflation:
    def test_modes_on_three_astartes(self):
        for mode, expected in (
            ("per_copy_all", 117),
            ("escalating", 108),
            ("flat_additional", 105),
        ):
            spec = replace(at.SPEC, inflation_mode=mode)
            result = evaluate_comp(
                spec, at.TABLE, at.HULLS, at.slots(at.ASTARTE, at.ASTARTE, at.ASTARTE)
            )
            assert sum(s.total_points for s in result.slots) == expected, mode

    def test_two_ashimmus_cost_twenty_each(self):
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.ASHIMMU, at.ASHIMMU))
        assert [s.total_points for s in result.slots] == [20, 20]

    def test_disabled_inflation(self):
        spec = replace(at.SPEC, inflation_enabled=False)
        result = evaluate_comp(spec, at.TABLE, at.HULLS, at.slots(at.ASTARTE, at.ASTARTE))
        assert [s.total_points for s in result.slots] == [33, 33]

    def test_inflation_points_function(self):
        assert inflation_points(0, 1, 3, "per_copy_all") == 0
        assert inflation_points(2, 3, 3, "escalating") == 6
        assert inflation_points(0, 3, 3, "flat_additional") == 0
        assert inflation_points(1, 3, 0, "per_copy_all") == 0


class TestLimits:
    def test_over_cap(self):
        comp = list(at.OF99_SET1)
        comp[-1] = at.ASHIMMU  # second Ashimmu: both go to 20
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(*comp))
        assert result.total_points == 215 and result.cap_status == c.CAP_OVER
        assert c.OVER_CAP in errors_of(result) and not result.is_legal

    def test_under_cap_is_info_with_unspent(self):
        comp = list(at.OF99_SET1)
        comp[6] = at.RIFTER  # Keres 12 -> Rifter 3
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(*comp))
        assert result.total_points == 191 and result.unspent_points == 9
        under = next(v for v in result.violations if v.code == c.UNDER_CAP)
        assert under.severity == c.SEVERITY_INFO and under.data["unspent"] == 9
        assert result.is_legal

    def test_logistics_limit(self):
        both = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.GUARDIAN, at.DEACON))
        assert c.GROUP_LIMIT_EXCEEDED in errors_of(both)
        limit = next(v for v in both.violations if v.code == c.GROUP_LIMIT_EXCEEDED)
        assert limit.data["units"] == 3 and limit.slot_nos == (1, 2)
        assert c.GROUP_LIMIT_EXCEEDED not in codes_of(
            evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.GUARDIAN))
        )
        assert c.GROUP_LIMIT_EXCEEDED not in codes_of(
            evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.DEACON, at.DEACON))
        )
        # a T1 support cruiser counts like a logistics cruiser
        assert c.GROUP_LIMIT_EXCEEDED in codes_of(
            evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.AUGOROR, at.DEACON))
        )

    def test_same_hull_limit_ag7(self):
        result = evaluate_comp(
            at.AG7_SPEC, at.TABLE, at.HULLS, at.slots(at.RIFTER, at.RIFTER, at.MAULUS)
        )
        assert c.OVER_SAME_HULL in errors_of(result)
        assert all(s.inflation_points == 0 for s in result.slots)

    def test_size_limit_on_battleships(self):
        result = evaluate_comp(
            at.SPEC, at.TABLE, at.HULLS, at.slots(at.RATTLESNAKE, at.RATTLESNAKE, at.RATTLESNAKE)
        )
        assert c.OVER_SIZE_LIMIT in errors_of(result)

    def test_wrong_slot_count_and_empty_slot(self):
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.RIFTER, None))
        assert c.WRONG_SLOT_COUNT in errors_of(result)
        assert c.EMPTY_SLOT in codes_of(result) and c.EMPTY_SLOT not in errors_of(result)

    def test_unlisted_and_illegal_hulls(self):
        hulls = dict(at.HULLS)
        hulls[at.RIFTER] = replace(at.HULLS[at.RIFTER], legality="banned")
        result = evaluate_comp(at.SPEC, at.TABLE, hulls, at.slots(at.RIFTER, 424242))
        assert {c.ILLEGAL_HULL, c.UNLISTED_HULL} <= errors_of(result)


class TestFlagship:
    def test_flagship_battleship_is_exempt_from_the_bs_cap(self):
        result = evaluate_comp(
            at.SPEC,
            at.TABLE,
            at.HULLS,
            at.slots(at.RATTLESNAKE, at.RATTLESNAKE, at.RATTLESNAKE, flagship_at=3),
        )
        assert c.OVER_SIZE_LIMIT not in codes_of(result)
        assert result.slots[2].effective_hull_size == "FLAG" and result.slots[2].hull_size == "BS"
        # flagship still counts for inflation: three copies pay 2 x 4 each
        assert [s.total_points for s in result.slots] == [61, 61, 61]

    def test_ineligible_flagship(self):
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.BHAALGORN, flagship_at=1))
        assert c.FLAGSHIP_NOT_ELIGIBLE in errors_of(result)

    def test_multiple_flagships_and_disabled(self):
        two = [
            SlotInput(1, at.RATTLESNAKE, is_flagship=True),
            SlotInput(2, at.RATTLESNAKE, is_flagship=True),
        ]
        assert c.MULTIPLE_FLAGSHIPS in errors_of(evaluate_comp(at.SPEC, at.TABLE, at.HULLS, two))
        assert c.FLAGSHIP_DISABLED in errors_of(
            evaluate_comp(at.AG7_SPEC, at.TABLE, at.HULLS, at.slots(at.RATTLESNAKE, flagship_at=1))
        )

    def test_banned_flagship_is_exempt(self):
        bans = [BanInput(at.RATTLESNAKE, None, "B")]
        result = evaluate_comp(
            at.SPEC,
            at.TABLE,
            at.HULLS,
            at.slots(at.RATTLESNAKE, at.RATTLESNAKE, flagship_at=1),
            bans,
        )
        assert result.slots[0].is_banned is False and result.slots[1].is_banned is True
        banned = next(v for v in result.violations if v.code == c.BANNED)
        assert banned.slot_nos == (2,)

    def test_bans_apply_to_both_teams(self):
        for side in ("A", "B"):
            bans = [BanInput(at.RATTLESNAKE, None, side)]
            result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.RATTLESNAKE), bans)
            assert c.BANNED in errors_of(result), side

    def test_class_bans(self):
        bans = [BanInput(None, "Command Ship", "B")]
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, at.slots(at.ASTARTE, at.ZEALOT), bans)
        assert result.slots[0].is_banned and not result.slots[1].is_banned


class TestUnique:
    def test_unique_declaration(self):
        slot = [SlotInput(1, at.RATTLESNAKE, is_unique=True)]
        result = evaluate_comp(at.SPEC, at.TABLE, at.HULLS, slot)
        declared = next(v for v in result.violations if v.code == c.UNIQUE_DECLARED)
        assert declared.data["extra_bans_for_opponent"] == 2
        assert c.UNIQUE_NOT_UNIQUE_HULL not in codes_of(result)
        result2 = evaluate_comp(
            at.SPEC, at.TABLE, at.HULLS, [SlotInput(1, at.RIFTER, is_unique=True)]
        )
        assert c.UNIQUE_NOT_UNIQUE_HULL in codes_of(result2)
