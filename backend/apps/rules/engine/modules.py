"""Module legality of one fit against a ruleset's module rules. Pure."""

import re
from collections.abc import Sequence

from apps.sde.constants import CATEGORY_DRONE, CATEGORY_IMPLANT, CATEGORY_MODULE

from . import codes
from .types import FitEvaluation, FitItemSpec, ModuleRulesSpec, Violation

# Categories the default meta-group rule applies to. Charges, implants, subsystems (Tech III) and
# deployables are only checked through explicit by_group rules.
DEFAULT_RULE_CATEGORIES = frozenset({CATEGORY_MODULE, CATEGORY_DRONE})

# Hardwiring implants carry no metaLevel in the SDE; CCP's "Meta 3" is the grade digit in the name
# (EE-603 is grade 3, SM-705 grade 5).
IMPLANT_GRADE_RE = re.compile(r"-(\d+)0(\d)$")


def implant_grade(name: str) -> int | None:
    m = IMPLANT_GRADE_RE.search(name.strip())
    return int(m.group(2)) if m else None


def evaluate_fit_modules(
    items: Sequence[FitItemSpec], rules: ModuleRulesSpec, is_flagship: bool = False
) -> FitEvaluation:
    found: dict[tuple[str, str], tuple[Violation, list[int]]] = {}

    def violate(
        code: str, severity: str, message: str, item: FitItemSpec, **data: int | str
    ) -> None:
        key = (code, item.name)
        if key in found:
            found[key][1].append(item.line_no)
            return
        found[key] = (Violation(code, severity, message, data=dict(data)), [item.line_no])

    for item in items:
        if item.type_id is None:
            violate(
                codes.UNRESOLVED_ITEM,
                codes.SEVERITY_WARNING,
                f"{item.name!r} is not a known item; not checked",
                item,
            )
            continue
        if any(re.search(p, item.name) for p in rules.allowed_name_patterns):
            continue
        banned_by = next((p for p in rules.banned_name_patterns if re.search(p, item.name)), None)
        if banned_by is not None:
            violate(
                codes.BANNED_TYPE,
                codes.SEVERITY_ERROR,
                f"{item.name} is banned",
                item,
                type_id=item.type_id,
                pattern=banned_by,
            )
            continue
        if item.type_id in rules.banned_type_ids:
            violate(
                codes.BANNED_TYPE,
                codes.SEVERITY_ERROR,
                f"{item.name} is banned",
                item,
                type_id=item.type_id,
            )
            continue

        if item.group_id is not None and item.group_id in rules.banned_group_ids:
            group = rules.group_names.get(item.group_id, "its group")
            violate(
                codes.BANNED_GROUP,
                codes.SEVERITY_ERROR,
                f"{item.name} is banned ({group} is not allowed in fits)",
                item,
                group_id=item.group_id,
            )
            continue

        # A rule naming the item's group is more specific than one naming its category and replaces it.
        matching = [
            r for r in rules.by_group if item.group_id is not None and item.group_id in r.group_ids
        ]
        if not matching:
            matching = [
                r
                for r in rules.by_group
                if item.category_id is not None and item.category_id in r.category_ids
            ]

        allowed: frozenset[int] | None = None
        specific = [r for r in matching if r.allowed_meta_group_ids is not None]
        if specific and specific[0].allowed_meta_group_ids is not None:
            allowed = specific[0].allowed_meta_group_ids
        elif item.category_id in DEFAULT_RULE_CATEGORIES:
            allowed = rules.default_allowed_meta_group_ids
        flagship = rules.flagship
        if (
            allowed is not None
            and is_flagship
            and flagship is not None
            and (not flagship.group_ids or item.group_id in flagship.group_ids)
        ):
            allowed = allowed | flagship.allowed_meta_group_ids
        if (
            allowed is not None
            and item.meta_group_id is not None
            and item.meta_group_id not in allowed
        ):
            meta_name = rules.meta_group_names.get(item.meta_group_id, str(item.meta_group_id))
            violate(
                codes.META_GROUP_NOT_ALLOWED,
                codes.SEVERITY_ERROR,
                f"{item.name} is {meta_name}; allowed: "
                + ", ".join(sorted(rules.meta_group_names.get(m, str(m)) for m in allowed)),
                item,
                meta_group_id=item.meta_group_id,
            )

        capped = [r for r in matching if r.max_meta_level is not None]
        if capped:
            rule = min(capped, key=lambda r: r.max_meta_level or 0)
            max_level = rule.max_meta_level
            assert max_level is not None
            level, source = item.meta_level, "sde"
            if level is None and item.category_id == CATEGORY_IMPLANT:
                level, source = implant_grade(item.name), "name"
            if level is None:
                violate(
                    codes.META_LEVEL_UNKNOWN,
                    codes.SEVERITY_WARNING,
                    f"{item.name}: meta level unknown; rule allows at most {max_level}",
                    item,
                    max_meta_level=max_level,
                )
            elif level > max_level:
                soft = rule.hull_scope == codes.HULL_SCOPE_BONUSED_ONLY
                suffix = (
                    " (only if the hull is bonused for it)"
                    if rule.hull_scope == codes.HULL_SCOPE_BONUSED_ONLY
                    else ""
                )
                violate(
                    codes.META_LEVEL_TOO_HIGH,
                    codes.SEVERITY_WARNING if soft else codes.SEVERITY_ERROR,
                    f"{item.name} is meta {level}; at most {max_level} allowed{suffix}",
                    item,
                    meta_level=level,
                    max_meta_level=max_level,
                    hull_scope=rule.hull_scope,
                    source=source,
                )

    violations = tuple(
        Violation(v.code, v.severity, v.message, tuple(sorted(set(lines))), v.data)
        for v, lines in found.values()
    )
    is_legal = all(v.severity != codes.SEVERITY_ERROR for v in violations)
    return FitEvaluation(violations=violations, is_legal=is_legal, item_count=len(items))
