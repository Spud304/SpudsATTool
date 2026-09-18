"""Build engine inputs from ORM rows. Cached per (ruleset, revision[, point version])."""

from collections import OrderedDict
from dataclasses import dataclass

from apps.sde.models import EveMetaGroup

from .engine.types import (
    FlagshipModuleRule,
    FlagshipRules,
    GroupLimit,
    GroupLimitMember,
    GroupModuleRule,
    HullIndex,
    HullSpec,
    ModuleRulesSpec,
    PointTable,
    RulesetSpec,
    SizeRule,
    StageSpec,
)
from .models import (
    Legality,
    ModuleNamePatternKind,
    ModuleRuleScope,
    PointTableVersion,
    Ruleset,
    Stage,
    TablePurpose,
)

CACHE_SIZE = 16


class NoPointTable(Exception):
    pass


@dataclass(frozen=True)
class EngineInputs:
    spec: RulesetSpec
    table: PointTable
    hulls: HullIndex


_cache: OrderedDict[tuple[int, int, int], EngineInputs] = OrderedDict()
_module_cache: OrderedDict[tuple[int, int], ModuleRulesSpec] = OrderedDict()


def clear_cache() -> None:
    _cache.clear()
    _module_cache.clear()


def module_rules_for(ruleset: Ruleset) -> ModuleRulesSpec:
    key = (ruleset.pk, ruleset.revision)
    cached = _module_cache.get(key)
    if cached is not None:
        _module_cache.move_to_end(key)
        return cached
    spec = build_module_rules(ruleset)
    _module_cache[key] = spec
    while len(_module_cache) > CACHE_SIZE:
        _module_cache.popitem(last=False)
    return spec


def build_module_rules(ruleset: Ruleset) -> ModuleRulesSpec:
    default_allowed: frozenset[int] | None = None
    by_group: list[GroupModuleRule] = []
    flagship: FlagshipModuleRule | None = None
    for rule in ruleset.module_rules.prefetch_related(
        "groups", "categories", "allowed_meta_groups"
    ):
        allowed = (
            frozenset(m.pk for m in rule.allowed_meta_groups.all())
            if rule.restricts_meta_groups
            else None
        )
        if rule.scope == ModuleRuleScope.DEFAULT:
            default_allowed = allowed
        elif rule.scope == ModuleRuleScope.FLAGSHIP:
            flagship = FlagshipModuleRule(
                allowed_meta_group_ids=allowed or frozenset(),
                group_ids=frozenset(g.pk for g in rule.groups.all()),
            )
        else:
            by_group.append(
                GroupModuleRule(
                    group_ids=frozenset(g.pk for g in rule.groups.all()),
                    category_ids=frozenset(c.pk for c in rule.categories.all()),
                    max_meta_level=rule.max_meta_level,
                    allowed_meta_group_ids=allowed,
                    hull_scope=rule.hull_scope,
                    note=rule.note,
                )
            )
    banned_groups = dict(ruleset.banned_module_groups.values_list("group_id", "group__name"))
    patterns = list(ruleset.module_name_patterns.values_list("kind", "pattern"))
    return ModuleRulesSpec(
        allowed_name_patterns=tuple(p for k, p in patterns if k == ModuleNamePatternKind.ALLOWED),
        banned_name_patterns=tuple(p for k, p in patterns if k == ModuleNamePatternKind.BANNED),
        default_allowed_meta_group_ids=default_allowed,
        by_group=tuple(by_group),
        flagship=flagship,
        banned_type_ids=frozenset(ruleset.banned_module_types.values_list("type_id", flat=True)),
        banned_group_ids=frozenset(banned_groups),
        meta_group_names=dict(EveMetaGroup.objects.values_list("id", "name")),
        group_names=dict(banned_groups.items()),
    )


def engine_inputs_for(ruleset: Ruleset, version: PointTableVersion | None = None) -> EngineInputs:
    if version is None:
        version = ruleset.point_versions.filter(purpose=TablePurpose.COST, is_current=True).first()
        if version is None:
            raise NoPointTable(f"{ruleset.code} has no current cost table")
    key = (ruleset.pk, ruleset.revision, version.pk)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached
    inputs = build_engine_inputs(ruleset, version)
    _cache[key] = inputs
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return inputs


def build_engine_inputs(ruleset: Ruleset, version: PointTableVersion) -> EngineInputs:
    spec = build_spec(ruleset)
    class_points: dict[str, int] = {}
    hull_points: dict[int, int] = {}
    for entry in version.entries.select_related("ship_class"):
        if entry.ship_class is not None:
            class_points[entry.ship_class.name] = entry.points
        elif entry.ship_id is not None:
            hull_points[entry.ship_id] = entry.points
    table = PointTable(version_id=version.pk, class_points=class_points, hull_points=hull_points)

    eligible_sizes = set(ruleset.flagship_eligible_sizes)
    eligible_meta = {m.pk for m in ruleset.flagship_eligible_meta_groups.all()}
    hulls: dict[int, HullSpec] = {}
    for rs in ruleset.ships.select_related("ship", "ship_class"):
        if rs.flagship_eligible is not None:
            eligible = rs.flagship_eligible
        else:
            eligible = (
                rs.legality == Legality.LEGAL
                and rs.hull_size in eligible_sizes
                and rs.ship.meta_group_id in eligible_meta
            )
        hulls[rs.ship_id] = HullSpec(
            type_id=rs.ship_id,
            name=rs.ship.name,
            hull_size=rs.hull_size,
            ship_class=rs.ship_class.name if rs.ship_class else None,
            legality=rs.legality,
            flagship_eligible=eligible,
            is_unique=rs.is_unique,
        )
    return EngineInputs(spec=spec, table=table, hulls=hulls)


def build_spec(ruleset: Ruleset) -> RulesetSpec:
    group_limits = tuple(
        GroupLimit(
            code=q.code,
            label=q.label,
            max=q.max,
            message=q.message,
            members=tuple(
                GroupLimitMember(
                    hull_size=m.hull_size,
                    ship_class=m.ship_class.name if m.ship_class else None,
                    type_id=m.ship_id,
                    weight=m.weight,
                )
                for m in q.members.select_related("ship_class")
            ),
        )
        for q in ruleset.group_limits.all()
    )
    return RulesetSpec(
        code=ruleset.code,
        fielded_pilots=ruleset.fielded_pilots,
        point_cap=ruleset.point_cap,
        max_same_hull=ruleset.max_same_hull,
        inflation_enabled=ruleset.duplicate_inflation_enabled,
        inflation_mode=ruleset.duplicate_inflation_mode,
        size_rules={
            h.hull_size: SizeRule(
                max_per_comp=h.max_per_comp, duplicate_surcharge=h.duplicate_surcharge
            )
            for h in ruleset.hull_sizes.all()
        },
        group_limits=group_limits,
        flagship=FlagshipRules(
            enabled=ruleset.flagship_enabled,
            immune_to_bans=ruleset.flagship_immune_to_bans,
            exempt_from_size_limit=ruleset.flagship_exempt_from_size_limit,
            counts_for_same_hull=ruleset.flagship_counts_for_same_hull,
            counts_for_inflation=ruleset.flagship_counts_for_inflation,
            lost_permanently=ruleset.flagship_lost_permanently,
        ),
        unique_ship_extra_bans=ruleset.unique_ship_extra_bans,
        unspent_points_to_opponent=ruleset.unspent_points_to_opponent,
        kill_points_source=ruleset.kill_points_source,
        point_threshold=ruleset.point_threshold,
        tiebreak_rule=ruleset.tiebreak_rule,
    )


def stage_spec(stage: Stage) -> StageSpec:
    return StageSpec(
        code=stage.code,
        best_of=stage.best_of,
        bans_per_side=stage.bans_per_side,
        ban_order_pattern=stage.ban_order_pattern,
        bans_are_blind=stage.bans_are_blind,
        ban_targets=stage.ban_targets,
        avalanche_enabled=stage.avalanche_enabled,
        avalanche_loser_bans=stage.avalanche_loser_bans,
        avalanche_winner_bans=stage.avalanche_winner_bans,
        avalanche_blind=stage.avalanche_blind,
        avalanche_persists=stage.avalanche_persists,
        flagship_uses=stage.flagship_uses,
    )
