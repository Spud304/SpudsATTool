"""Turn a validated ruleset document into rows. Resolve every name first, then write in one transaction."""

import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.importing import ImportFailed, ImportReport
from apps.sde import constants as sde
from apps.sde.models import EveCategory, EveGroup, EveMetaGroup, EveType
from apps.sde.resolve import resolve_names as resolve_sde_names

from . import yaml_io
from .constants import GROUP_HULL_SIZES, T1_SUPPORT_HULL_SIZES
from .inference import HullFacts, infer_aliases, infer_prefix
from .models import (
    BannedModuleGroup,
    BannedModuleType,
    GroupLimit,
    GroupLimitMember,
    HullSizeRule,
    Legality,
    MappingSource,
    ModuleRule,
    ModuleRuleScope,
    PointTableEntry,
    PointTableVersion,
    Ruleset,
    RulesetShip,
    ShipClass,
    Stage,
    TablePurpose,
    TextSection,
    Tournament,
)
from .yaml_io import RulesetDocument, ShipDoc

log = logging.getLogger(__name__)

SDE_MISSING = ImportFailed(
    "the SDE mirror is empty", "run `manage.py import_sde --check-latest` first"
)


@dataclass
class Resolved:
    hulls: dict[str, EveType] = field(default_factory=dict)  # by name, ships only
    types: dict[str, EveType] = field(default_factory=dict)  # by name, any category
    groups: dict[str, EveGroup] = field(default_factory=dict)
    categories: dict[str, EveCategory] = field(default_factory=dict)
    meta_groups: dict[str, EveMetaGroup] = field(default_factory=dict)


@dataclass(frozen=True)
class ShipPlan:
    hull: EveType
    class_name: str | None
    hull_size: str
    size_is_override: bool
    legality: str
    flagship_eligible: bool | None
    is_unique: bool
    mapping_source: str


def _resolve(names: set[str], queryset, label: str, errors: list[str]) -> dict:
    found, problems = resolve_sde_names(names, queryset, label)
    errors.extend(problems)
    return found


def resolve_names(doc: RulesetDocument) -> Resolved:
    if not EveType.objects.exists():
        raise SDE_MISSING
    errors: list[str] = []
    out = Resolved()
    hull_names = {s.hull for s in doc.ships} | set(doc.banned_hulls) | set(doc.unique_hulls)
    for limit in doc.group_limits:
        hull_names |= {m.hull for m in limit.members if m.hull}
    if doc.point_table:
        hull_names |= {o.hull for o in doc.point_table.hull_overrides}
    ships = EveType.objects.filter(
        published=True, removed=False, group__category_id=sde.CATEGORY_SHIP
    )
    out.hulls = _resolve(hull_names, ships, "hull", errors)

    group_names: set[str] = set()
    category_names: set[str] = set()
    meta_names = set(doc.ruleset.flagship.eligible_meta_groups)
    type_names: set[str] = set()
    if doc.module_rules:
        meta_names |= set(doc.module_rules.default.allowed_meta_groups)
        for rule in doc.module_rules.by_group:
            group_names |= set(rule.groups)
            category_names |= set(rule.categories)
            meta_names |= set(rule.allowed_meta_groups or [])
        type_names |= set(doc.module_rules.banned_types)
        group_names |= set(doc.module_rules.banned_groups)
        if doc.module_rules.flagship:
            meta_names |= set(doc.module_rules.flagship.allowed_meta_groups)
            group_names |= set(doc.module_rules.flagship.groups)
    out.groups = _resolve(group_names, EveGroup.objects.all(), "SDE group", errors)
    out.categories = _resolve(category_names, EveCategory.objects.all(), "SDE category", errors)
    out.meta_groups = _resolve(meta_names, EveMetaGroup.objects.all(), "meta group", errors)
    out.types = _resolve(
        type_names, EveType.objects.filter(published=True, removed=False), "type", errors
    )
    if errors:
        raise ImportFailed(
            f"{len(errors)} unresolved name(s):\n" + "\n".join(errors),
            "check spelling against sde_eve_type / sde_eve_group names; run import_sde if the SDE is stale",
        )
    return out


def plan_ships(doc: RulesetDocument, resolved: Resolved, report: ImportReport) -> list[ShipPlan]:
    """Explicit entries win, then prefix inference, then aliases. Every planned ship gets a size."""
    class_sizes = {c.name: c.size for c in doc.ship_classes}
    explicit: dict[str, ShipDoc] = {s.hull: s for s in doc.ships}
    banned = set(doc.banned_hulls)
    unique = set(doc.unique_hulls)

    inferred: dict[int, tuple[str, str]] = {}
    if doc.ruleset.ships_inference != "none":
        candidates = EveType.objects.filter(
            published=True, removed=False, group__category_id=sde.CATEGORY_SHIP
        ).select_related("meta_group")
        facts = [
            HullFacts(
                t.pk, t.name, t.group_id, t.meta_group.name if t.meta_group else None, t.faction_id
            )
            for t in candidates
            if t.name not in explicit
        ]
        for type_id, cls in infer_prefix(facts, class_sizes).items():
            inferred[type_id] = (cls, MappingSource.INFERRED_PREFIX)
        if doc.ruleset.ships_inference == "prefix_and_aliases":
            rest = [f for f in facts if f.type_id not in inferred]
            aliased, warnings = infer_aliases(rest, class_sizes)
            for type_id, cls in aliased.items():
                inferred[type_id] = (cls, MappingSource.INFERRED_ALIAS)
            for w in warnings:
                report.warn(f"alias inference: {w}")
        if inferred:
            for t in EveType.objects.filter(pk__in=inferred):
                resolved.hulls.setdefault(t.name, t)

    plans: list[ShipPlan] = []
    errors: list[str] = []
    seen: set[int] = set()

    def size_for(
        hull: EveType, explicit_size: str | None, class_name: str | None
    ) -> tuple[str | None, bool]:
        if explicit_size:
            return explicit_size, True
        if class_name and class_name in class_sizes:
            return class_sizes[class_name], False
        if hull.name in T1_SUPPORT_HULL_SIZES:
            return T1_SUPPORT_HULL_SIZES[hull.name], False
        return GROUP_HULL_SIZES.get(hull.group_id), False

    for entry in doc.ships:
        hull = resolved.hulls[entry.hull]
        size, override = size_for(hull, entry.size, entry.class_)
        if size is None:
            errors.append(f"{entry.hull}: no hull size (give it a class or a size)")
            continue
        seen.add(hull.pk)
        plans.append(
            ShipPlan(
                hull=hull,
                class_name=entry.class_,
                hull_size=size,
                size_is_override=override,
                legality=Legality.BANNED
                if (entry.hull in banned or entry.legality == "banned")
                else Legality.LEGAL,
                flagship_eligible=entry.flagship_eligible,
                is_unique=entry.unique or entry.hull in unique,
                mapping_source=MappingSource.EXPLICIT,
            )
        )
    for type_id, (cls, source) in inferred.items():
        hull = next(t for t in resolved.hulls.values() if t.pk == type_id)
        if hull.pk in seen:
            continue
        size, _ = size_for(hull, None, cls)
        if size is None:
            errors.append(f"{hull.name}: inferred class {cls!r} but no hull size")
            continue
        seen.add(hull.pk)
        plans.append(
            ShipPlan(
                hull,
                cls,
                size,
                False,
                Legality.BANNED if hull.name in banned else Legality.LEGAL,
                None,
                hull.name in unique,
                source,
            )
        )
    for name in sorted((banned | unique) - {p.hull.name for p in plans}):
        hull = resolved.hulls[name]
        size, _ = size_for(hull, None, None)
        if size is None:
            errors.append(f"{name}: banned/unique hull has no hull size (give it a ships entry)")
            continue
        plans.append(
            ShipPlan(
                hull,
                None,
                size,
                False,
                Legality.BANNED if name in banned else Legality.LEGAL,
                None,
                name in unique,
                MappingSource.EXPLICIT,
            )
        )
    if errors:
        raise ImportFailed(
            f"{len(errors)} unsized hull(s):\n" + "\n".join(errors),
            "add a `size:` to the ships entry or map the hull to a class",
        )
    report.derived["ships_inferred"] = sum(
        1 for p in plans if p.mapping_source != MappingSource.EXPLICIT
    )
    return plans


def effective_document(doc: RulesetDocument, plans: list[ShipPlan]) -> RulesetDocument:
    """The document with inferred ships made explicit, so it compares equal to an export."""
    ships = [
        ShipDoc.model_validate(
            {
                "hull": p.hull.name,
                "class": p.class_name,
                "size": p.hull_size if p.size_is_override else None,
                "flagship_eligible": p.flagship_eligible,
            }
        )
        for p in plans
        if p.class_name or p.size_is_override or p.flagship_eligible is not None
    ]
    return doc.model_copy(
        update={
            "ships": ships,
            "banned_hulls": sorted(p.hull.name for p in plans if p.legality == Legality.BANNED),
            "unique_hulls": sorted(p.hull.name for p in plans if p.is_unique),
        }
    )


def import_ruleset(
    doc: RulesetDocument,
    *,
    report: ImportReport,
    replace_points: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> Ruleset:
    from .exporter import export_document

    resolved = resolve_names(doc)
    plans = plan_ships(doc, resolved, report)
    effective = effective_document(doc, plans)
    new_hash = yaml_io.document_hash(effective)

    existing = (
        Ruleset.objects.filter(tournament__code=doc.tournament.code)
        .select_related("tournament")
        .first()
    )
    if existing is not None:
        if existing.tournament.verified and not doc.verified and not force:
            raise ImportFailed(
                f"{doc.tournament.code} is verified; the document is not",
                "pass --force to replace a verified ruleset with an unverified document",
            )
        if yaml_io.document_hash(export_document(existing)) == new_hash:
            report.warn(f"{doc.tournament.code}: unchanged, nothing written")
            report.finish()
            return existing
    if not doc.verified:
        report.warn(f"{doc.tournament.code}: document is marked unverified")

    with transaction.atomic():
        ruleset = _write(doc, effective, plans, resolved, report, replace_points, new_hash)
        if dry_run:
            transaction.set_rollback(True)
            report.warn("dry run: all changes rolled back")
    report.finish()
    return ruleset


def _write(doc, effective, plans, resolved, report, replace_points, new_hash) -> Ruleset:
    t = doc.tournament
    tournament, _ = Tournament.objects.update_or_create(
        code=t.code,
        defaults={
            "name": t.name,
            "organiser": t.organiser,
            "server": t.server,
            "year": t.year,
            "starts_on": t.starts_on,
            "ends_on": t.ends_on,
            "rules_url": t.rules_url or "",
            "verified": doc.verified,
            "notes": doc.notes,
        },
    )
    k = doc.ruleset
    ruleset, created = Ruleset.objects.update_or_create(
        tournament=tournament,
        defaults={
            "fielded_pilots": k.fielded_pilots,
            "point_cap": k.point_cap,
            "max_same_hull": k.max_same_hull,
            "duplicate_inflation_enabled": k.duplicate_inflation.enabled,
            "duplicate_inflation_mode": k.duplicate_inflation.mode,
            "flagship_enabled": k.flagship.enabled,
            "flagship_immune_to_bans": k.flagship.immune_to_bans,
            "flagship_exempt_from_size_limit": k.flagship.exempt_from_size_limit,
            "flagship_counts_for_same_hull": k.flagship.counts_for_same_hull,
            "flagship_counts_for_inflation": k.flagship.counts_for_inflation,
            "flagship_lost_permanently": k.flagship.lost_permanently,
            "flagship_eligible_sizes": list(k.flagship.eligible_sizes),
            "unique_ship_extra_bans": k.unique_ship_extra_bans,
            "unspent_points_to_opponent": k.unspent_points_to_opponent,
            "kill_points_source": k.kill_points_source,
            "point_threshold": k.match.point_threshold,
            "tiebreak_rule": k.match.tiebreak,
            "roster_max": k.roster.max,
            "merc_max": k.roster.merc_max,
            "ships_inference": k.ships_inference,
            "extra": k.extra,
            "source_hash": new_hash,
            "imported_at": timezone.now(),
        },
    )
    ruleset.flagship_eligible_meta_groups.set(
        [resolved.meta_groups[n] for n in k.flagship.eligible_meta_groups]
    )
    report.derived["ruleset"] = 1 if created else 0

    ruleset.hull_sizes.all().delete()
    HullSizeRule.objects.bulk_create(
        HullSizeRule(
            ruleset=ruleset,
            hull_size=h.size,
            label=h.label,
            max_per_comp=h.max_per_comp,
            duplicate_surcharge=h.duplicate_surcharge,
            sort_order=i,
        )
        for i, h in enumerate(doc.hull_sizes)
    )
    report.derived["hull_sizes"] = len(doc.hull_sizes)

    # Ship classes: upsert by name, deactivate the missing ones (old point versions still point at them).
    classes: dict[str, ShipClass] = {c.name: c for c in ruleset.ship_classes.all()}
    for i, c in enumerate(doc.ship_classes):
        row = classes.get(c.name)
        if row is None:
            row = ShipClass(ruleset=ruleset, name=c.name)
            classes[c.name] = row
        elif row.hull_size != c.size:
            report.warn(f"class {c.name!r}: hull size changed {row.hull_size} -> {c.size}")
        row.hull_size, row.sort_order, row.active = c.size, i, True
        row.save()
    doc_class_names = {c.name for c in doc.ship_classes}
    for name, row in classes.items():
        if name not in doc_class_names and row.active:
            row.active = False
            row.save(update_fields=["active"])
            report.warn(f"class {name!r} no longer listed; kept inactive")
    report.derived["ship_classes"] = len(doc.ship_classes)

    ruleset.group_limits.all().delete()
    for i, q in enumerate(doc.group_limits):
        limit = GroupLimit.objects.create(
            ruleset=ruleset,
            code=q.code,
            label=q.label,
            max=q.max,
            message=q.message,
            sort_order=i,
        )
        GroupLimitMember.objects.bulk_create(
            GroupLimitMember(
                limit=limit,
                hull_size=m.hull_size,
                ship_class=classes[m.class_] if m.class_ else None,
                ship=resolved.hulls[m.hull] if m.hull else None,
                weight=m.weight,
            )
            for m in q.members
        )
    report.derived["group_limits"] = len(doc.group_limits)

    ruleset.stages.all().delete()
    Stage.objects.bulk_create(
        Stage(
            ruleset=ruleset,
            code=s.code,
            label=s.label or "",
            sort_order=i,
            best_of=s.best_of,
            bans_per_side=s.bans_per_side,
            ban_order_pattern=s.ban_order,
            bans_are_blind=s.blind,
            ban_targets=s.ban_targets,
            ban_deadline_minutes=s.deadline_minutes,
            avalanche_enabled=s.avalanche is not None,
            avalanche_loser_bans=s.avalanche.loser if s.avalanche else 0,
            avalanche_winner_bans=s.avalanche.winner if s.avalanche else 0,
            avalanche_blind=s.avalanche.blind if s.avalanche else True,
            avalanche_persists=s.avalanche.persists if s.avalanche else True,
            flagship_uses=s.flagship_uses,
        )
        for i, s in enumerate(doc.stages)
    )
    report.derived["stages"] = len(doc.stages)

    # Ruleset ships: upsert by hull, delete the ones no longer planned.
    current = {rs.ship_id: rs for rs in ruleset.ships.all()}
    planned_ids = set()
    for p in plans:
        planned_ids.add(p.hull.pk)
        row = current.get(p.hull.pk) or RulesetShip(ruleset=ruleset, ship=p.hull)
        row.ship_class = classes[p.class_name] if p.class_name else None
        row.hull_size = p.hull_size
        row.hull_size_is_override = p.size_is_override
        row.legality = p.legality
        row.flagship_eligible = p.flagship_eligible
        row.is_unique = p.is_unique
        row.mapping_source = p.mapping_source
        row.save()
    removed = ruleset.ships.exclude(ship_id__in=planned_ids)
    removed_count = removed.count()
    removed.delete()
    report.derived["ships"] = len(plans)
    if removed_count:
        report.warn(f"{removed_count} ruleset ship(s) removed (no longer in the document)")

    if doc.point_table is not None:
        _write_points(
            ruleset, doc, effective, classes, resolved, report, replace_points, TablePurpose.COST
        )
    if doc.kill_table is not None:
        _write_points(
            ruleset, doc, effective, classes, resolved, report, replace_points, TablePurpose.KILL
        )

    ruleset.module_rules.all().delete()
    ruleset.banned_module_types.all().delete()
    if doc.module_rules is not None:
        mr = doc.module_rules
        default = ModuleRule.objects.create(
            ruleset=ruleset, scope=ModuleRuleScope.DEFAULT, restricts_meta_groups=True
        )
        default.allowed_meta_groups.set(
            [resolved.meta_groups[n] for n in mr.default.allowed_meta_groups]
        )
        for i, r in enumerate(mr.by_group):
            rule = ModuleRule.objects.create(
                ruleset=ruleset,
                scope=ModuleRuleScope.GROUP,
                sort_order=i,
                max_meta_level=r.max_meta_level,
                hull_scope=r.hulls,
                note=r.note,
                restricts_meta_groups=r.allowed_meta_groups is not None,
            )
            rule.groups.set([resolved.groups[g] for g in r.groups])
            rule.categories.set([resolved.categories[c] for c in r.categories])
            rule.allowed_meta_groups.set(
                [resolved.meta_groups[n] for n in (r.allowed_meta_groups or [])]
            )
        if mr.flagship is not None:
            flag = ModuleRule.objects.create(
                ruleset=ruleset, scope=ModuleRuleScope.FLAGSHIP, restricts_meta_groups=True
            )
            flag.allowed_meta_groups.set(
                [resolved.meta_groups[n] for n in mr.flagship.allowed_meta_groups]
            )
            flag.groups.set([resolved.groups[g] for g in mr.flagship.groups])
        BannedModuleType.objects.bulk_create(
            BannedModuleType(ruleset=ruleset, type=resolved.types[n]) for n in mr.banned_types
        )
        ruleset.banned_module_groups.all().delete()
        BannedModuleGroup.objects.bulk_create(
            BannedModuleGroup(ruleset=ruleset, group=resolved.groups[g]) for g in mr.banned_groups
        )
        report.derived["module_rules"] = 1 + len(mr.by_group) + (1 if mr.flagship else 0)

    ruleset.text_sections.all().delete()
    TextSection.objects.bulk_create(
        TextSection(
            ruleset=ruleset,
            sort_order=i,
            heading=s.heading,
            body_markdown=s.body,
            source_url=s.source_url or "",
        )
        for i, s in enumerate(doc.text_sections)
    )

    Ruleset.objects.filter(pk=ruleset.pk).update(revision=F("revision") + 1)
    ruleset.refresh_from_db()
    log.info(
        "ruleset %s imported (revision %d): %s", ruleset.code, ruleset.revision, report.derived
    )
    return ruleset


def _write_points(
    ruleset, doc, effective, classes, resolved, report, replace_points, purpose
) -> None:
    if purpose == TablePurpose.COST:
        table = doc.point_table
        entries = [
            (classes[c.name], None, c.points) for c in doc.ship_classes if c.points is not None
        ]
        entries += [(None, resolved.hulls[o.hull], o.points) for o in table.hull_overrides]
        content_hash = yaml_io.points_hash(doc)
    else:
        table = doc.kill_table
        entries = [(classes[c.name], None, c.points) for c in table.classes if c.name in classes]
        missing = [c.name for c in table.classes if c.name not in classes]
        if missing:
            raise ImportFailed(
                f"kill_table names classes not in ship_classes: {missing}",
                "add them to ship_classes",
            )
        entries += [(None, resolved.hulls[o.hull], o.points) for o in table.hull_overrides]
        content_hash = yaml_io.points_hash(
            doc.model_copy(
                update={
                    "ship_classes": [
                        yaml_io.ShipClassDoc(name=c.name, size="FR", points=c.points)
                        for c in table.classes
                    ],
                    "point_table": table,
                }
            )
        )

    current = ruleset.point_versions.filter(purpose=purpose, is_current=True).first()
    meta = {
        "label": table.label,
        "source_url": table.source_url or "",
        "effective_from": table.effective_from,
    }
    if current is not None and current.content_hash == content_hash:
        for k, v in meta.items():
            setattr(current, k, v)
        current.save()
        report.derived[f"{purpose}_table"] = 0
        return
    if current is not None and replace_points:
        if current.is_pinned():
            raise ImportFailed(
                f"{purpose} table v{current.version_no} is pinned by recorded matches",
                "drop --replace-points; a new version will be created instead",
            )
        current.entries.all().delete()
        for k, v in meta.items():
            setattr(current, k, v)
        current.content_hash = content_hash
        current.imported_at = timezone.now()
        current.save()
        version = current
        report.warn(f"{purpose} table v{current.version_no} rewritten in place")
    else:
        last_no = (
            ruleset.point_versions.filter(purpose=purpose)
            .order_by("-version_no")
            .values_list("version_no", flat=True)
            .first()
        )
        if current is not None:
            current.is_current = False
            current.save(update_fields=["is_current"])
        version = PointTableVersion.objects.create(
            ruleset=ruleset,
            purpose=purpose,
            version_no=(last_no or 0) + 1,
            is_current=True,
            content_hash=content_hash,
            imported_at=timezone.now(),
            **meta,
        )
        if current is not None:
            report.warn(
                f"{purpose} table: new version {version.version_no} (v{current.version_no} kept)"
            )
    PointTableEntry.objects.bulk_create(
        PointTableEntry(version=version, ship_class=cls, ship=ship, points=points)
        for cls, ship, points in entries
    )
    report.derived[f"{purpose}_table"] = len(entries)
