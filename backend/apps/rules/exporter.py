"""ORM -> RulesetDocument -> canonical YAML. import(export(x)) is a no-op."""

from . import yaml_io
from .models import Legality, ModuleRuleScope, Ruleset, TablePurpose
from .yaml_io import RulesetDocument


def export_document(ruleset: Ruleset) -> RulesetDocument:
    t = ruleset.tournament
    classes = list(ruleset.ship_classes.filter(active=True).order_by("sort_order"))
    class_by_pk = {c.pk: c.name for c in classes}
    cost = ruleset.point_versions.filter(purpose=TablePurpose.COST, is_current=True).first()
    cost_points: dict[int, int] = {}
    cost_overrides: list[dict] = []
    if cost is not None:
        for e in cost.entries.select_related("ship"):
            if e.ship_class_id is not None:
                cost_points[e.ship_class_id] = e.points
            elif e.ship is not None:
                cost_overrides.append({"hull": e.ship.name, "points": e.points})

    ships = []
    banned: list[str] = []
    unique: list[str] = []
    for rs in ruleset.ships.select_related("ship", "ship_class").order_by("ship__name"):
        if rs.legality == Legality.BANNED:
            banned.append(rs.ship.name)
        if rs.is_unique:
            unique.append(rs.ship.name)
        if rs.ship_class is None and not rs.hull_size_is_override and rs.flagship_eligible is None:
            continue
        ships.append(
            {
                "hull": rs.ship.name,
                "class": rs.ship_class.name if rs.ship_class else None,
                "size": rs.hull_size if rs.hull_size_is_override else None,
                "flagship_eligible": rs.flagship_eligible,
            }
        )

    group_limits = []
    for q in ruleset.group_limits.prefetch_related("members__ship", "members__ship_class"):
        group_limits.append(
            {
                "code": q.code,
                "label": q.label,
                "max": q.max,
                "message": q.message,
                "members": [
                    {
                        "hull_size": m.hull_size,
                        "class": m.ship_class.name if m.ship_class else None,
                        "hull": m.ship.name if m.ship else None,
                        "weight": m.weight,
                    }
                    for m in q.members.all()
                ],
            }
        )

    stages = []
    for s in ruleset.stages.all():
        stage = {
            "code": s.code,
            "label": s.label or None,
            "best_of": s.best_of,
            "bans_per_side": s.bans_per_side,
            "ban_order": s.ban_order_pattern,
            "blind": s.bans_are_blind,
            "ban_targets": s.ban_targets,
            "deadline_minutes": s.ban_deadline_minutes,
            "avalanche": (
                {
                    "loser": s.avalanche_loser_bans,
                    "winner": s.avalanche_winner_bans,
                    "blind": s.avalanche_blind,
                    "persists": s.avalanche_persists,
                }
                if s.avalanche_enabled
                else None
            ),
            "flagship_uses": s.flagship_uses,
        }
        stages.append(stage)

    module_rules = None
    rules = list(
        ruleset.module_rules.prefetch_related("groups", "categories", "allowed_meta_groups")
    )
    if rules:
        default = next((r for r in rules if r.scope == ModuleRuleScope.DEFAULT), None)
        flag = next((r for r in rules if r.scope == ModuleRuleScope.FLAGSHIP), None)
        module_rules = {
            "default": {
                "allowed_meta_groups": sorted(m.name for m in default.allowed_meta_groups.all())
                if default
                else []
            },
            "by_group": [
                {
                    "groups": sorted(g.name for g in r.groups.all()),
                    "categories": sorted(c.name for c in r.categories.all()),
                    "max_meta_level": r.max_meta_level,
                    "allowed_meta_groups": sorted(m.name for m in r.allowed_meta_groups.all())
                    if r.restricts_meta_groups
                    else None,
                    "hulls": r.hull_scope,
                    "note": r.note,
                }
                for r in rules
                if r.scope == ModuleRuleScope.GROUP
            ],
            "banned_types": sorted(
                b.type.name for b in ruleset.banned_module_types.select_related("type")
            ),
            "banned_groups": sorted(
                b.group.name for b in ruleset.banned_module_groups.select_related("group")
            ),
            "allowed_name_patterns": list(
                ruleset.module_name_patterns.filter(kind="allowed").values_list(
                    "pattern", flat=True
                )
            ),
            "banned_name_patterns": list(
                ruleset.module_name_patterns.filter(kind="banned").values_list("pattern", flat=True)
            ),
            "flagship": (
                {
                    "allowed_meta_groups": sorted(m.name for m in flag.allowed_meta_groups.all()),
                    "groups": sorted(g.name for g in flag.groups.all()),
                }
                if flag
                else None
            ),
        }

    data = {
        "schema_version": yaml_io.SCHEMA_VERSION,
        "verified": t.verified,
        "notes": t.notes,
        "tournament": {
            "code": t.code,
            "name": t.name,
            "organiser": t.organiser,
            "server": t.server,
            "year": t.year,
            "starts_on": t.starts_on,
            "ends_on": t.ends_on,
            "rules_url": t.rules_url or None,
        },
        "ruleset": {
            "fielded_pilots": ruleset.fielded_pilots,
            "point_cap": ruleset.point_cap,
            "max_same_hull": ruleset.max_same_hull,
            "duplicate_inflation": {
                "enabled": ruleset.duplicate_inflation_enabled,
                "mode": ruleset.duplicate_inflation_mode,
            },
            "flagship": {
                "enabled": ruleset.flagship_enabled,
                "immune_to_bans": ruleset.flagship_immune_to_bans,
                "exempt_from_size_limit": ruleset.flagship_exempt_from_size_limit,
                "counts_for_same_hull": ruleset.flagship_counts_for_same_hull,
                "counts_for_inflation": ruleset.flagship_counts_for_inflation,
                "lost_permanently": ruleset.flagship_lost_permanently,
                "eligible_sizes": list(ruleset.flagship_eligible_sizes),
                "eligible_meta_groups": [
                    m.name for m in ruleset.flagship_eligible_meta_groups.order_by("id")
                ],
            },
            "unique_ship_extra_bans": ruleset.unique_ship_extra_bans,
            "unspent_points_to_opponent": ruleset.unspent_points_to_opponent,
            "kill_points_source": ruleset.kill_points_source,
            "match": {
                "tiebreak": ruleset.tiebreak_rule,
                "point_threshold": ruleset.point_threshold,
            },
            "roster": {"max": ruleset.roster_max, "merc_max": ruleset.merc_max},
            "ships_inference": ruleset.ships_inference,
            "extra": ruleset.extra,
        },
        "hull_sizes": [
            {
                "size": h.hull_size,
                "label": h.label,
                "max_per_comp": h.max_per_comp,
                "duplicate_surcharge": h.duplicate_surcharge,
            }
            for h in ruleset.hull_sizes.all()
        ],
        "group_limits": group_limits,
        "stages": stages,
        "ship_classes": [
            {"name": c.name, "size": c.hull_size, "points": cost_points.get(c.pk) if cost else None}
            for c in classes
        ],
        "ships": ships,
        "point_table": (
            {
                "label": cost.label,
                "source_url": cost.source_url or None,
                "effective_from": cost.effective_from,
                "hull_overrides": cost_overrides,
            }
            if cost is not None
            else None
        ),
        "kill_table": _kill_table(ruleset, class_by_pk),
        "banned_hulls": banned,
        "unique_hulls": unique,
        "module_rules": module_rules,
        "text_sections": [
            {"heading": s.heading, "body": s.body_markdown, "source_url": s.source_url or None}
            for s in ruleset.text_sections.all()
        ],
    }
    return RulesetDocument.model_validate(data)


def _kill_table(ruleset: Ruleset, class_by_pk: dict[int, str]) -> dict | None:
    kill = ruleset.point_versions.filter(purpose=TablePurpose.KILL, is_current=True).first()
    if kill is None:
        return None
    classes, overrides = [], []
    for e in kill.entries.select_related("ship"):
        if e.ship_class_id is not None and e.ship_class_id in class_by_pk:
            classes.append({"name": class_by_pk[e.ship_class_id], "points": e.points})
        elif e.ship is not None:
            overrides.append({"hull": e.ship.name, "points": e.points})
    return {
        "label": kill.label,
        "source_url": kill.source_url or None,
        "effective_from": kill.effective_from,
        "hull_overrides": overrides,
        "classes": classes,
    }


def export_ruleset(ruleset: Ruleset) -> str:
    return yaml_io.dump_document(export_document(ruleset))
