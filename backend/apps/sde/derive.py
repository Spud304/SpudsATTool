"""Typed tables derived from the raw layer. One transaction so readers switch builds atomically."""

import logging
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.core.importing import ImportReport

from .constants import RAW_ITER_CHUNK, TYPED_BATCH_SIZE
from .models import (
    EveCategory,
    EveFaction,
    EveGroup,
    EveMetaGroup,
    EveRace,
    EveType,
    SdeBuild,
    SdeRawRecord,
)

log = logging.getLogger(__name__)

# (SDE field, model field, cast). Absent fields stay None.
GROUP_FIELDS = (
    ("anchorable", "anchorable", bool),
    ("anchored", "anchored", bool),
    ("fittableNonSingleton", "fittable_non_singleton", bool),
    ("useBasePrice", "use_base_price", bool),
)
TYPE_FIELDS = (
    ("techLevel", "tech_level", int),
    ("metaLevel", "meta_level", int),
    ("mass", "mass", float),
    ("volume", "volume", float),
    ("packagedVolume", "packaged_volume", float),
    ("capacity", "capacity", float),
    ("portionSize", "portion_size", int),
    ("basePrice", "base_price", float),
    ("marketGroupID", "market_group_id", int),
    ("variationParentTypeID", "variation_parent_type_id", int),
    ("iconID", "icon_id", int),
    ("graphicID", "graphic_id", int),
)


def _name(data: dict) -> str:
    name = data.get("name")
    if isinstance(name, dict):
        return str(name.get("en") or next(iter(name.values()), ""))
    return str(name or "")


def _apply(instance: models.Model, data: dict, spec: tuple[tuple[str, str, Callable], ...]) -> None:
    for sde_field, model_field, cast in spec:
        value = data.get(sde_field)
        setattr(instance, model_field, cast(value) if value is not None else None)


def _raw(file: str) -> Iterator[SdeRawRecord]:
    return SdeRawRecord.objects.filter(file=file).order_by("pk").iterator(chunk_size=RAW_ITER_CHUNK)


def _upsert[M: models.Model](model: type[M], rows: Sequence[M], fields: list[str]) -> None:
    if rows:
        model.objects.bulk_create(
            rows,
            batch_size=TYPED_BATCH_SIZE,
            update_conflicts=True,
            unique_fields=["id"],
            update_fields=fields,
        )


def _flag_missing(model: type[models.Model], seen: set[int]) -> int:
    """Rows not produced by this derivation are no longer in the current set."""
    return model.objects.filter(removed=False).exclude(id__in=seen).update(removed=True)


def derive_all(build: int, release_date: datetime | None, report: ImportReport) -> None:
    with transaction.atomic():
        categories = _derive_categories(report)
        group_category = _derive_groups(categories, report)
        meta_groups = _derive_meta_groups(report)
        factions = _derive_factions(report)
        races = _derive_races(report)
        _derive_types(group_category, meta_groups, factions, races, report)
        report.finish()
        SdeBuild.objects.update_or_create(
            build=build,
            defaults={
                "release_date": release_date,
                "imported_at": timezone.now(),
                "source": report.source[:300],
                "files": sorted(report.files),
                "counts": report.as_dict(),
                "duration_s": report.duration_s,
            },
        )


def _derive_categories(report: ImportReport) -> set[int]:
    rows, seen = [], set()
    for raw in _raw("categories"):
        cid = int(raw.key)
        seen.add(cid)
        rows.append(
            EveCategory(
                id=cid,
                name=_name(raw.data),
                published=bool(raw.data.get("published", False)),
                removed=raw.removed,
            )
        )
    _upsert(EveCategory, rows, ["name", "published", "removed"])
    _flag_missing(EveCategory, seen)
    report.derived["categories"] = len(rows)
    return seen


def _derive_groups(categories: set[int], report: ImportReport) -> dict[int, int]:
    rows, group_category, skipped = [], {}, 0
    for raw in _raw("groups"):
        gid = int(raw.key)
        cat = raw.data.get("categoryID")
        if cat is None or int(cat) not in categories:
            skipped += 1
            continue
        group = EveGroup(
            id=gid,
            category_id=int(cat),
            name=_name(raw.data),
            published=bool(raw.data.get("published", False)),
            removed=raw.removed,
        )
        _apply(group, raw.data, GROUP_FIELDS)
        for _, field, _ in GROUP_FIELDS:
            if getattr(group, field) is None:
                setattr(group, field, False)
        rows.append(group)
        group_category[gid] = int(cat)
    _upsert(
        EveGroup,
        rows,
        ["category", "name", "published", "removed"] + [f for _, f, _ in GROUP_FIELDS],
    )
    _flag_missing(EveGroup, set(group_category))
    report.derived["groups"] = len(rows)
    if skipped:
        report.warn(f"groups: {skipped} records skipped (unknown or missing categoryID)")
    return group_category


def _derive_meta_groups(report: ImportReport) -> set[int]:
    rows = [
        EveMetaGroup(
            id=int(raw.key),
            name=_name(raw.data),
            icon_id=raw.data.get("iconID"),
            icon_suffix=str(raw.data.get("iconSuffix") or ""),
        )
        for raw in _raw("metaGroups")
        if not raw.removed
    ]
    _upsert(EveMetaGroup, rows, ["name", "icon_id", "icon_suffix"])
    report.derived["metaGroups"] = len(rows)
    return {r.id for r in rows}


def _derive_factions(report: ImportReport) -> set[int]:
    rows = [
        EveFaction(
            id=int(raw.key),
            name=_name(raw.data),
            corporation_id=raw.data.get("corporationID"),
            solar_system_id=raw.data.get("solarSystemID"),
            member_races=list(raw.data.get("memberRaces") or []),
        )
        for raw in _raw("factions")
        if not raw.removed
    ]
    _upsert(EveFaction, rows, ["name", "corporation_id", "solar_system_id", "member_races"])
    report.derived["factions"] = len(rows)
    return {r.id for r in rows}


def _derive_races(report: ImportReport) -> set[int]:
    rows = [
        EveRace(id=int(raw.key), name=_name(raw.data)) for raw in _raw("races") if not raw.removed
    ]
    _upsert(EveRace, rows, ["name"])
    report.derived["races"] = len(rows)
    return {r.id for r in rows}


def _derive_types(
    group_category: dict[int, int],
    meta_groups: set[int],
    factions: set[int],
    races: set[int],
    report: ImportReport,
) -> None:
    wanted_categories = set(settings.SDE_TYPE_CATEGORIES)
    rows: list[EveType] = []
    seen: set[int] = set()
    unknown_group = 0
    nulled: dict[str, int] = {"faction": 0, "meta_group": 0, "race": 0}

    def _fk(value: Any, valid: set[int], field: str) -> int | None:
        if value is None:
            return None
        if int(value) in valid:
            return int(value)
        nulled[field] += 1
        return None

    def flush() -> None:
        _upsert(
            EveType,
            rows,
            ["group", "name", "published", "removed", "faction", "meta_group", "race"]
            + [f for _, f, _ in TYPE_FIELDS],
        )
        rows.clear()

    for raw in _raw("types"):
        gid = raw.data.get("groupID")
        if gid is None or int(gid) not in group_category:
            unknown_group += 1
            continue
        if group_category[int(gid)] not in wanted_categories:
            continue
        tid = int(raw.key)
        seen.add(tid)
        eve_type = EveType(
            id=tid,
            group_id=int(gid),
            name=_name(raw.data),
            published=bool(raw.data.get("published", False)),
            removed=raw.removed,
            faction_id=_fk(raw.data.get("factionID"), factions, "faction"),
            meta_group_id=_fk(raw.data.get("metaGroupID"), meta_groups, "meta_group"),
            race_id=_fk(raw.data.get("raceID"), races, "race"),
        )
        _apply(eve_type, raw.data, TYPE_FIELDS)
        rows.append(eve_type)
        if len(rows) >= TYPED_BATCH_SIZE:
            flush()
    flush()
    flagged = _flag_missing(EveType, seen)
    report.derived["types"] = len(seen)
    if unknown_group:
        report.warn(f"types: {unknown_group} records skipped (groupID not in groups)")
    for field, count in nulled.items():
        if count:
            report.warn(f"types: {count} records had an unknown {field} id; set to null")
    log.info("types: %d derived, %d flagged removed", len(seen), flagged)
