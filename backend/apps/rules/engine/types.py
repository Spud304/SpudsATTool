"""Frozen inputs and outputs of the rules engine."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HullSpec:
    """How one ruleset sees one hull."""

    type_id: int
    name: str
    hull_size: str | None
    ship_class: str | None
    legality: str
    flagship_eligible: bool
    is_unique: bool = False


@dataclass(frozen=True)
class SizeRule:
    max_per_comp: int | None
    duplicate_surcharge: int


@dataclass(frozen=True)
class GroupLimitMember:
    hull_size: str | None = None
    ship_class: str | None = None
    type_id: int | None = None
    weight: int = 1


@dataclass(frozen=True)
class GroupLimit:
    code: str
    label: str
    max: int
    members: tuple[GroupLimitMember, ...]
    message: str = ""


@dataclass(frozen=True)
class StageSpec:
    code: str
    best_of: int
    bans_per_side: int
    ban_order_pattern: str
    bans_are_blind: bool = False
    ban_targets: str = "hull"
    avalanche_enabled: bool = False
    avalanche_loser_bans: int = 0
    avalanche_winner_bans: int = 0
    avalanche_blind: bool = True
    avalanche_persists: bool = True
    flagship_uses: int = 0


@dataclass(frozen=True)
class FlagshipRules:
    enabled: bool = False
    immune_to_bans: bool = True
    exempt_from_size_limit: bool = True
    counts_for_same_hull: bool = True
    counts_for_inflation: bool = True
    lost_permanently: bool = True


@dataclass(frozen=True)
class RulesetSpec:
    code: str
    fielded_pilots: int
    point_cap: int
    max_same_hull: int | None
    inflation_enabled: bool
    inflation_mode: str
    size_rules: Mapping[str, SizeRule]
    group_limits: tuple[GroupLimit, ...] = ()
    flagship: FlagshipRules = FlagshipRules()
    unique_ship_extra_bans: int = 0
    unspent_points_to_opponent: bool = True
    kill_points_source: str = "comp_cost"
    point_threshold: int | None = None  # differential band for scoreboard colours
    tiebreak_rule: str = "none"


@dataclass(frozen=True)
class PointTable:
    version_id: int
    class_points: Mapping[str, int]
    hull_points: Mapping[int, int] = field(default_factory=dict)


HullIndex = Mapping[int, HullSpec]


@dataclass(frozen=True)
class SlotInput:
    slot_no: int
    type_id: int | None
    is_flagship: bool = False
    is_unique: bool = False
    has_links: bool = False  # the chosen fit carries a command burst; set by the caller


@dataclass(frozen=True)
class BanInput:
    type_id: int | None
    ship_class: str | None
    made_by_side: str  # recorded for stats only; a ban applies to both teams
    kind: str = "standard"


@dataclass(frozen=True)
class Violation:
    code: str
    severity: str
    message: str
    slot_nos: tuple[int, ...] = ()
    data: Mapping[str, int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class SlotEval:
    slot_no: int
    type_id: int | None
    name: str | None
    hull_size: str | None
    effective_hull_size: str | None
    base_points: int
    inflation_points: int
    total_points: int
    copy_index: int
    copies_of_hull: int
    is_flagship: bool
    is_banned: bool
    has_links: bool
    link_index: int | None
    flags: tuple[str, ...]


@dataclass(frozen=True)
class CompEvaluation:
    slots: tuple[SlotEval, ...]
    total_points: int
    point_cap: int
    cap_status: str
    unspent_points: int
    violations: tuple[Violation, ...]
    is_legal: bool
    point_table_version_id: int


@dataclass(frozen=True)
class SideScore:
    fielded_points: int
    unspent_points: int
    points_lost: int
    handicap_conceded: int
    points_conceded: int


@dataclass(frozen=True)
class RoundScore:
    us: SideScore
    opp: SideScore
    differential: int  # opp.points_conceded - us.points_conceded; positive means we lead
    leader: str  # "US" | "OPP" | "TIED"
    differential_indicator: str
    tiebreak_hint: str | None


@dataclass(frozen=True)
class FitItemSpec:
    """One EFT line (module, charge, drone, implant, cargo) after SDE resolution; type_id None when unresolved."""

    line_no: int
    name: str
    type_id: int | None
    category_id: int | None = None
    group_id: int | None = None
    meta_group_id: int | None = None
    meta_level: int | None = None
    quantity: int = 1
    offline: bool = False


@dataclass(frozen=True)
class GroupModuleRule:
    group_ids: frozenset[int] = frozenset()
    category_ids: frozenset[int] = frozenset()
    max_meta_level: int | None = None
    allowed_meta_group_ids: frozenset[int] | None = None
    hull_scope: str = "any"
    note: str = ""


@dataclass(frozen=True)
class FlagshipModuleRule:
    allowed_meta_group_ids: frozenset[int]
    group_ids: frozenset[int] = frozenset()  # empty means every module family


@dataclass(frozen=True)
class ModuleRulesSpec:
    default_allowed_meta_group_ids: frozenset[int] | None = None
    by_group: tuple[GroupModuleRule, ...] = ()
    flagship: FlagshipModuleRule | None = None
    banned_type_ids: frozenset[int] = frozenset()
    banned_group_ids: frozenset[int] = frozenset()
    meta_group_names: Mapping[int, str] = field(default_factory=dict)
    group_names: Mapping[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FitEvaluation:
    violations: tuple[Violation, ...]
    is_legal: bool
    item_count: int
