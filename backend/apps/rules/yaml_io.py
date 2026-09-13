"""Ruleset YAML documents: schema (pydantic), strict loading, canonical dumping. No Django here."""

import hashlib
import json
from datetime import date
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from apps.core.importing import ImportFailed

from .constants import HULL_SIZES, SCHEMA_VERSION

HullSize = Literal["FLAG", "BS", "BC", "CR", "LC", "DE", "FR", "LF", "IN", "CV"]
SCHEMA_DOC = "docs/rulesets.md"


class DocumentInvalid(ImportFailed):
    pass


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)


class TournamentDoc(_Base):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,15}$")
    name: str
    organiser: Literal["ccp", "community"]
    server: Literal["tranquility", "thunderdome"] = "tranquility"
    year: int
    starts_on: date | None = None
    ends_on: date | None = None
    rules_url: str | None = None


class InflationDoc(_Base):
    enabled: bool = False
    mode: Literal["per_copy_all", "escalating", "flat_additional"] = "per_copy_all"


class FlagshipDoc(_Base):
    enabled: bool = False
    immune_to_bans: bool = True
    exempt_from_size_limit: bool = True
    counts_for_same_hull: bool = True
    counts_for_inflation: bool = True
    lost_permanently: bool = True
    eligible_sizes: list[HullSize] = ["BS"]
    eligible_meta_groups: list[str] = ["Tech I", "Tech II", "Faction"]


class MatchDoc(_Base):
    tiebreak: Literal["none", "potential_dps_t0", "points_remaining", "custom"] = "none"
    point_threshold: int | None = None  # differential band for the scoreboard colours


class RosterDoc(_Base):
    max: int | None = None
    merc_max: int | None = None


class RulesetKnobs(_Base):
    fielded_pilots: int = Field(ge=1, le=20)
    point_cap: int = Field(gt=0)
    max_same_hull: int | None = None
    duplicate_inflation: InflationDoc = InflationDoc()
    flagship: FlagshipDoc = FlagshipDoc()
    unique_ship_extra_bans: int = 0
    unspent_points_to_opponent: bool = True
    kill_points_source: Literal["comp_cost", "kill_table"] = "comp_cost"
    match: MatchDoc = MatchDoc()
    roster: RosterDoc = RosterDoc()
    ships_inference: Literal["none", "prefix", "prefix_and_aliases"] = "prefix"
    extra: dict[str, Any] = {}


class HullSizeDoc(_Base):
    size: HullSize
    label: str
    max_per_comp: int | None = None
    duplicate_surcharge: int = 0


class GroupLimitMemberDoc(_Base):
    hull_size: HullSize | None = None
    class_: str | None = Field(default=None, alias="class")
    hull: str | None = None
    weight: int = 1


class GroupLimitDoc(_Base):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    max: int = Field(ge=0)
    message: str = ""
    members: list[GroupLimitMemberDoc] = Field(min_length=1)


class AvalancheDoc(_Base):
    loser: int = Field(ge=0)
    winner: int = Field(ge=0)
    blind: bool = True
    persists: bool = True


class StageDoc(_Base):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str | None = None
    best_of: Literal[1, 3, 5, 7]
    bans_per_side: int = Field(ge=0)
    ban_order: str = ""
    blind: bool = False
    ban_targets: Literal["hull", "class"] = "hull"
    deadline_minutes: int | None = None
    avalanche: AvalancheDoc | None = None
    flagship_uses: int = 0


class ShipClassDoc(_Base):
    name: str
    size: HullSize
    points: int | None = None


class ShipDoc(_Base):
    hull: str
    class_: str | None = Field(default=None, alias="class")
    size: HullSize | None = None
    legality: Literal["legal", "banned"] = "legal"
    flagship_eligible: bool | None = None
    unique: bool = False


class HullOverrideDoc(_Base):
    hull: str
    points: int


class PointTableDoc(_Base):
    label: str = ""
    source_url: str | None = None
    effective_from: date | None = None
    hull_overrides: list[HullOverrideDoc] = []


class KillClassDoc(_Base):
    name: str
    points: int


class KillTableDoc(PointTableDoc):
    classes: list[KillClassDoc] = []


class ModuleDefaultDoc(_Base):
    allowed_meta_groups: list[str]


class ModuleRuleDoc(_Base):
    groups: list[str] = []
    categories: list[str] = []
    max_meta_level: int | None = None
    allowed_meta_groups: list[str] | None = None
    hulls: Literal["any", "bonused_only"] = "any"
    note: str = ""


class FlagshipModuleDoc(_Base):
    allowed_meta_groups: list[str]
    groups: list[str] = []


class ModuleRulesDoc(_Base):
    default: ModuleDefaultDoc
    by_group: list[ModuleRuleDoc] = []
    banned_types: list[str] = []
    flagship: FlagshipModuleDoc | None = None


class TextSectionDoc(_Base):
    heading: str
    body: str
    source_url: str | None = None


class RulesetDocument(_Base):
    schema_version: int
    verified: bool = True
    notes: str = ""
    tournament: TournamentDoc
    ruleset: RulesetKnobs
    hull_sizes: list[HullSizeDoc] = Field(min_length=1)
    group_limits: list[GroupLimitDoc] = []
    stages: list[StageDoc] = Field(min_length=1)
    ship_classes: list[ShipClassDoc] = []
    ships: list[ShipDoc] = []
    point_table: PointTableDoc | None = None
    kill_table: KillTableDoc | None = None
    banned_hulls: list[str] = []
    unique_hulls: list[str] = []
    module_rules: ModuleRulesDoc | None = None
    text_sections: list[TextSectionDoc] = []

    @model_validator(mode="after")
    def _cross_checks(self) -> "RulesetDocument":
        problems: list[str] = []
        if self.schema_version != SCHEMA_VERSION:
            problems.append(f"schema_version: expected {SCHEMA_VERSION}, got {self.schema_version}")

        sizes = [h.size for h in self.hull_sizes]
        known = set(sizes)
        for size in _duplicates(sizes):
            problems.append(f"hull_sizes: size {size} listed more than once")
        for h in self.hull_sizes:
            if h.size == "FLAG" and h.duplicate_surcharge:
                problems.append(
                    "hull_sizes[FLAG]: the flagship pseudo-size cannot carry a duplicate_surcharge"
                )
        flag = self.ruleset.flagship
        needs_flag_row = flag.enabled and flag.exempt_from_size_limit
        if needs_flag_row and "FLAG" not in known:
            problems.append(
                "hull_sizes: a FLAG entry is required when flagship.exempt_from_size_limit is on"
            )
        if not needs_flag_row and "FLAG" in known:
            problems.append(
                "hull_sizes: FLAG is only meaningful with flagship.enabled and exempt_from_size_limit"
            )
        for size in flag.eligible_sizes:
            if size not in known:
                problems.append(f"ruleset.flagship.eligible_sizes: {size} is not in hull_sizes")

        for i, limit in enumerate(self.group_limits):
            for j, member in enumerate(limit.members):
                selectors = [member.hull_size, member.class_, member.hull]
                if sum(s is not None for s in selectors) != 1:
                    problems.append(
                        f"group_limits[{i}].members[{j}]: exactly one of hull_size, class, hull is required"
                    )
                if member.hull_size is not None and member.hull_size not in known:
                    problems.append(
                        f"group_limits[{i}].members[{j}]: size {member.hull_size} is not in hull_sizes"
                    )
        for code in _duplicates([q.code for q in self.group_limits]):
            problems.append(f"group_limits: code {code} listed more than once")

        for code in _duplicates([s.code for s in self.stages]):
            problems.append(f"stages: code {code} listed more than once")
        for i, stage in enumerate(self.stages):
            order = stage.ban_order
            if set(order) - {"A", "B"}:
                problems.append(f"stages[{i}].ban_order: only the letters A and B are allowed")
            elif order.count("A") != stage.bans_per_side or order.count("B") != stage.bans_per_side:
                problems.append(
                    f"stages[{i}].ban_order: needs exactly {stage.bans_per_side} A and {stage.bans_per_side} B"
                )
            if stage.avalanche is not None and stage.best_of == 1:
                problems.append(f"stages[{i}].avalanche: only meaningful in a best-of series")
            if stage.flagship_uses and not flag.enabled:
                problems.append(
                    f"stages[{i}].flagship_uses: flagships are disabled in this ruleset"
                )

        class_names = [c.name for c in self.ship_classes]
        for name in _duplicates(class_names):
            problems.append(f"ship_classes: {name!r} listed more than once")
        class_set = set(class_names)
        for i, cls in enumerate(self.ship_classes):
            if cls.size not in known:
                problems.append(f"ship_classes[{i}]: size {cls.size} is not in hull_sizes")
            if self.point_table is not None and cls.points is None:
                problems.append(
                    f"ship_classes[{i}] ({cls.name}): points required when point_table is present"
                )
            if self.point_table is None and cls.points is not None:
                problems.append(
                    f"ship_classes[{i}] ({cls.name}): points given but there is no point_table"
                )

        for hull in _duplicates([s.hull for s in self.ships]):
            problems.append(f"ships: {hull!r} listed more than once")
        banned = set(self.banned_hulls)
        unique = set(self.unique_hulls)
        for i, ship in enumerate(self.ships):
            if ship.class_ is not None and ship.class_ not in class_set:
                problems.append(
                    f"ships[{i}] ({ship.hull}): class {ship.class_!r} is not in ship_classes"
                )
            if ship.size is not None and ship.size not in known:
                problems.append(f"ships[{i}] ({ship.hull}): size {ship.size} is not in hull_sizes")
            if (
                ship.hull in banned
                and "legality" in ship.model_fields_set
                and ship.legality == "legal"
            ):
                problems.append(
                    f"ships[{i}] ({ship.hull}): marked legal but listed in banned_hulls"
                )
            if ship.hull in unique and "unique" in ship.model_fields_set and not ship.unique:
                problems.append(
                    f"ships[{i}] ({ship.hull}): unique false but listed in unique_hulls"
                )
        for hull in _duplicates(self.banned_hulls):
            problems.append(f"banned_hulls: {hull!r} listed more than once")
        for hull in _duplicates(self.unique_hulls):
            problems.append(f"unique_hulls: {hull!r} listed more than once")
        if self.point_table is not None:
            for hull in _duplicates([o.hull for o in self.point_table.hull_overrides]):
                problems.append(f"point_table.hull_overrides: {hull!r} listed more than once")

        wants_kill = self.ruleset.kill_points_source == "kill_table"
        if wants_kill and self.kill_table is None:
            problems.append("kill_table: required when ruleset.kill_points_source is kill_table")
        if not wants_kill and self.kill_table is not None:
            problems.append(
                "kill_table: only allowed when ruleset.kill_points_source is kill_table"
            )

        if self.module_rules is not None:
            for i, rule in enumerate(self.module_rules.by_group):
                if not rule.groups and not rule.categories:
                    problems.append(f"module_rules.by_group[{i}]: needs groups or categories")
                if rule.max_meta_level is None and rule.allowed_meta_groups is None:
                    problems.append(
                        f"module_rules.by_group[{i}]: needs max_meta_level or allowed_meta_groups"
                    )

        if problems:
            raise ValueError("\n".join(problems))
        return self


def _duplicates(values: list) -> list:
    seen: set = set()
    out: list = []
    for v in values:
        if v in seen and v not in out:
            out.append(v)
        seen.add(v)
    return out


class _UniqueKeyLoader(yaml.SafeLoader):
    """PyYAML silently keeps the last duplicate key; that hides exactly the copy-paste mistakes we want caught."""

    def construct_mapping(self, node, deep=False):
        seen: set = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def load_ruleset_document(text: str) -> RulesetDocument:
    """Parse and validate; every problem is reported at once as `path: message`."""
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise DocumentInvalid(
            f"YAML syntax error: {exc}", f"fix the YAML; see {SCHEMA_DOC}"
        ) from exc
    if not isinstance(data, dict):
        raise DocumentInvalid(
            "the document must be a mapping at the top level", f"see {SCHEMA_DOC}"
        )
    try:
        return RulesetDocument.model_validate(data)
    except ValidationError as exc:
        lines: list[str] = []
        for err in exc.errors():
            path = ".".join(str(p) for p in err["loc"]) or "<document>"
            msg = err["msg"]
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, ") :]
            for part in msg.split("\n"):
                lines.append(part if path == "<document>" else f"{path}: {part}")
        raise DocumentInvalid(
            f"{len(lines)} problem(s) in the ruleset document:\n" + "\n".join(lines),
            f"fix the listed paths and re-run; see {SCHEMA_DOC}",
        ) from exc


class _Flow(dict):
    """Marker: emit this mapping in flow style `{ a: 1, b: 2 }`."""


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(
    _Flow, lambda d, data: d.represent_mapping("tag:yaml.org,2002:map", data, flow_style=True)
)


def _prune(d: dict, drop: dict[str, Any]) -> dict:
    return {k: v for k, v in d.items() if not (k in drop and v == drop[k])}


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def dump_document(doc: RulesetDocument) -> str:
    """Canonical YAML: fixed key order, flow style for one-line entries, sorted hull lists."""
    data = doc.model_dump(mode="json", by_alias=True)
    order = {s: i for i, s in enumerate(HULL_SIZES)}
    data["hull_sizes"] = [
        _Flow(_drop_none(h)) for h in sorted(data["hull_sizes"], key=lambda h: order[h["size"]])
    ]
    for limit in data["group_limits"]:
        limit["members"] = [_Flow(_drop_none(m)) for m in limit["members"]]
    data["stages"] = [_Flow(_drop_none(s)) for s in data["stages"]]
    for stage in data["stages"]:
        if "avalanche" in stage:
            stage["avalanche"] = _Flow(stage["avalanche"])
    data["ship_classes"] = [_Flow(_drop_none(c)) for c in data["ship_classes"]]
    ship_defaults = {
        "class": None,
        "size": None,
        "legality": "legal",
        "flagship_eligible": None,
        "unique": False,
    }
    data["ships"] = [
        _Flow(_prune(s, ship_defaults)) for s in sorted(data["ships"], key=lambda s: s["hull"])
    ]
    data["banned_hulls"] = sorted(data["banned_hulls"])
    data["unique_hulls"] = sorted(data["unique_hulls"])
    if data.get("point_table"):
        data["point_table"]["hull_overrides"] = [
            _Flow(o) for o in sorted(data["point_table"]["hull_overrides"], key=lambda o: o["hull"])
        ]
    if data.get("kill_table"):
        data["kill_table"]["classes"] = [_Flow(c) for c in data["kill_table"]["classes"]]
        data["kill_table"]["hull_overrides"] = [
            _Flow(o) for o in data["kill_table"]["hull_overrides"]
        ]
    # Name lists are sets in meaning; sort them so hand-written and exported documents agree.
    data["ruleset"]["flagship"]["eligible_meta_groups"] = sorted(
        data["ruleset"]["flagship"]["eligible_meta_groups"]
    )
    if data.get("module_rules"):
        mr = data["module_rules"]
        mr["default"]["allowed_meta_groups"] = sorted(mr["default"]["allowed_meta_groups"])
        mr["default"] = _Flow(mr["default"])
        for rule in mr["by_group"]:
            for key in ("groups", "categories"):
                rule[key] = sorted(rule[key])
            if rule.get("allowed_meta_groups"):
                rule["allowed_meta_groups"] = sorted(rule["allowed_meta_groups"])
        mr["by_group"] = [_Flow(_drop_none(r)) for r in mr["by_group"]]
        mr["banned_types"] = sorted(mr["banned_types"])
        if mr.get("flagship"):
            mr["flagship"]["allowed_meta_groups"] = sorted(mr["flagship"]["allowed_meta_groups"])
            mr["flagship"]["groups"] = sorted(mr["flagship"]["groups"])
            mr["flagship"] = _Flow(mr["flagship"])
    return yaml.dump(
        data,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=200,
        default_flow_style=False,
    )


def document_hash(doc: RulesetDocument) -> str:
    return hashlib.sha256(dump_document(doc).encode("utf-8")).hexdigest()


def points_hash(doc: RulesetDocument) -> str:
    """Identity of the cost table: class points plus hull overrides, order-independent."""
    classes = sorted((c.name, c.points) for c in doc.ship_classes if c.points is not None)
    overrides = sorted(
        (o.hull, o.points) for o in (doc.point_table.hull_overrides if doc.point_table else [])
    )
    return hashlib.sha256(json.dumps([classes, overrides]).encode("utf-8")).hexdigest()
