"""Bulk name lookup against SDE tables: exact first, then case-insensitive; unknown and ambiguous names reported."""

import re
from collections.abc import Iterable
from typing import Any

from django.db import models


def resolve_names[M: models.Model](
    names: Iterable[str], queryset: Any, label: str
) -> tuple[dict[str, M], list[str]]:
    """Map each requested name to exactly one row of `queryset`; problems come back as messages."""
    wanted = {n for n in names if n}
    found: dict[str, M] = {}
    errors: list[str] = []
    if not wanted:
        return found, errors
    by_name: dict[str, list[M]] = {}
    for row in queryset.filter(name__in=wanted):
        by_name.setdefault(row.name, []).append(row)
    lowered = {n.lower(): n for n in wanted if n not in by_name}
    if lowered:
        pattern = "^(" + "|".join(re.escape(n) for n in lowered) + ")$"
        for row in queryset.filter(name__iregex=pattern):
            original = lowered.get(row.name.lower())
            if original:
                by_name.setdefault(original, []).append(row)
    for name in sorted(wanted):
        matches = by_name.get(name, [])
        if not matches:
            errors.append(f"unknown {label}: {name!r}")
        elif len(matches) > 1:
            ids = ", ".join(str(m.pk) for m in matches)
            errors.append(f"ambiguous {label}: {name!r} matches ids {ids}")
        else:
            found[name] = matches[0]
    return found, errors
