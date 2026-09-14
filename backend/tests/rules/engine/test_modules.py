"""Pure module-legality tests; ids are arbitrary."""

from apps.rules.engine import (
    FitItemSpec,
    FlagshipModuleRule,
    GroupModuleRule,
    ModuleRulesSpec,
    evaluate_fit_modules,
    implant_grade,
)
from apps.rules.engine import codes as c

T1, T2, FACTION, ABYSSAL, T3 = 1, 2, 4, 15, 14
MODULE, CHARGE, DRONE, IMPLANT, SUBSYSTEM = 7, 8, 18, 20, 32
WEB, DAMP, IMPLANT_GROUP = 65, 208, 749

RULES = ModuleRulesSpec(
    default_allowed_meta_group_ids=frozenset({T1, T2}),
    by_group=(
        GroupModuleRule(group_ids=frozenset({DAMP}), max_meta_level=4, hull_scope="bonused_only"),
        GroupModuleRule(category_ids=frozenset({IMPLANT}), max_meta_level=3),
    ),
    flagship=FlagshipModuleRule(allowed_meta_group_ids=frozenset({FACTION})),
    banned_type_ids=frozenset({999}),
    banned_group_ids=frozenset({303}),
    group_names={303: "Booster"},
    meta_group_names={T1: "Tech I", T2: "Tech II", FACTION: "Faction", ABYSSAL: "Abyssal"},
)


def item(name, type_id=1, category=MODULE, group=WEB, meta=T2, level=5, line=3):
    return FitItemSpec(
        line_no=line,
        name=name,
        type_id=type_id,
        category_id=category,
        group_id=group,
        meta_group_id=meta,
        meta_level=level,
    )


def codes_of(ev):
    return {(v.code, v.severity) for v in ev.violations}


def test_t2_module_legal():
    ev = evaluate_fit_modules([item("Stasis Webifier II")], RULES)
    assert ev.is_legal and ev.violations == () and ev.item_count == 1


def test_faction_module_fails_default_and_flagship_relaxes():
    web = item("Federation Navy Stasis Webifier", meta=FACTION, level=8)
    ev = evaluate_fit_modules([web], RULES)
    assert not ev.is_legal and codes_of(ev) == {(c.META_GROUP_NOT_ALLOWED, "error")}
    assert "Faction" in ev.violations[0].message
    assert evaluate_fit_modules([web], RULES, is_flagship=True).is_legal


def test_flagship_relaxation_limited_to_listed_groups():
    rules = ModuleRulesSpec(
        default_allowed_meta_group_ids=frozenset({T1, T2}),
        flagship=FlagshipModuleRule(
            allowed_meta_group_ids=frozenset({FACTION}), group_ids=frozenset({DAMP})
        ),
    )
    web = item("Federation Navy Stasis Webifier", meta=FACTION)
    assert not evaluate_fit_modules([web], rules, is_flagship=True).is_legal


def test_abyssal_fails_and_banned_type():
    ev = evaluate_fit_modules(
        [
            item("Abyssal Stasis Webifier", meta=ABYSSAL, level=None),
            item("Banned Thing", type_id=999),
        ],
        RULES,
    )
    assert codes_of(ev) == {(c.META_GROUP_NOT_ALLOWED, "error"), (c.BANNED_TYPE, "error")}


def test_banned_group_catches_drugs():
    pill = item("Standard Blue Pill Booster", category=IMPLANT, group=303, meta=T1, level=None)
    ev = evaluate_fit_modules([pill], RULES)
    assert not ev.is_legal and codes_of(ev) == {(c.BANNED_GROUP, "error")}
    assert "Booster" in ev.violations[0].message


def test_dampener_meta_cap_soft_when_bonused_only_hard_otherwise():
    damp = item("Remote Sensor Dampener II", group=DAMP, meta=T2, level=5)
    ev = evaluate_fit_modules([damp], RULES)
    assert ev.is_legal and codes_of(ev) == {(c.META_LEVEL_TOO_HIGH, "warning")}
    assert ev.violations[0].data["hull_scope"] == "bonused_only"
    hard = ModuleRulesSpec(
        by_group=(GroupModuleRule(group_ids=frozenset({DAMP}), max_meta_level=4),)
    )
    ev = evaluate_fit_modules([damp], hard)
    assert not ev.is_legal and codes_of(ev) == {(c.META_LEVEL_TOO_HIGH, "error")}
    ok = item("Phased Scoped Remote Sensor Dampener", group=DAMP, meta=T1, level=4)
    assert evaluate_fit_modules([ok], hard).violations == ()


def test_charges_and_subsystems_skip_default_rule():
    items = [
        item("Imperial Navy Multifrequency M", category=CHARGE, group=83, meta=FACTION, level=None),
        item(
            "Legion Defensive - Augmented Plating",
            category=SUBSYSTEM,
            group=954,
            meta=T3,
            level=None,
        ),
        item("Warrior II", category=DRONE, group=100, meta=T2, level=5),
    ]
    assert evaluate_fit_modules(items, RULES).violations == ()
    faction_drone = item("Gecko", category=DRONE, group=100, meta=FACTION, level=None)
    assert not evaluate_fit_modules([faction_drone], RULES).is_legal


def test_implant_grade_heuristic():
    assert implant_grade("Zainou 'Gypsy' CPU Management EE-603") == 3
    assert implant_grade("Inherent Implants 'Noble' Hull Upgrades HG-1003") == 3
    assert implant_grade("Zainou 'Gnome' Shield Management SM-705") == 5
    assert implant_grade("Genolution Core Augmentation CA-1") is None
    ok = item(
        "Zainou 'Gypsy' CPU Management EE-603",
        category=IMPLANT,
        group=IMPLANT_GROUP,
        meta=None,
        level=None,
    )
    high = item(
        "Zainou 'Gnome' Shield Management SM-705",
        category=IMPLANT,
        group=IMPLANT_GROUP,
        meta=None,
        level=None,
    )
    unknown = item(
        "Genolution Core Augmentation CA-1",
        category=IMPLANT,
        group=IMPLANT_GROUP,
        meta=None,
        level=None,
    )
    assert evaluate_fit_modules([ok], RULES).violations == ()
    ev = evaluate_fit_modules([ok, high, unknown], RULES)
    assert not ev.is_legal
    by_code = {v.code: v for v in ev.violations}
    too_high = by_code[c.META_LEVEL_TOO_HIGH]
    assert too_high.severity == "error" and too_high.data["source"] == "name"
    assert by_code[c.META_LEVEL_UNKNOWN].severity == "warning"


def test_unresolved_is_warning_and_lines_merge():
    items = [
        FitItemSpec(line_no=3, name="Mystery Module", type_id=None),
        FitItemSpec(line_no=9, name="Mystery Module", type_id=None),
    ]
    ev = evaluate_fit_modules(items, RULES)
    assert ev.is_legal
    assert ev.violations[0].code == c.UNRESOLVED_ITEM and ev.violations[0].slot_nos == (3, 9)


def test_no_rules_means_everything_legal():
    assert evaluate_fit_modules([item("x", meta=ABYSSAL)], ModuleRulesSpec()).violations == ()
