"""Comp legality and points. Total functions: user data never raises, it produces violations."""

from collections import defaultdict
from collections.abc import Sequence

from . import codes
from .types import (
    BanInput,
    CompEvaluation,
    GroupLimit,
    HullIndex,
    HullSpec,
    PointTable,
    RulesetSpec,
    SlotEval,
    SlotInput,
    Violation,
)


def inflation_points(copy_index: int, copies: int, surcharge: int, mode: str) -> int:
    """Surcharge paid by one copy of a duplicated hull under the ruleset's mode."""
    if copies <= 1 or surcharge <= 0:
        return 0
    if mode == codes.MODE_PER_COPY_ALL:
        return (copies - 1) * surcharge
    if mode == codes.MODE_ESCALATING:
        return copy_index * surcharge
    if mode == codes.MODE_FLAT_ADDITIONAL:
        return surcharge if copy_index > 0 else 0
    return 0


def base_points(hull: HullSpec, table: PointTable) -> int | None:
    if hull.type_id in table.hull_points:
        return table.hull_points[hull.type_id]
    if hull.ship_class is not None:
        return table.class_points.get(hull.ship_class)
    return None


def effective_hull_size(hull: HullSpec | None, is_flagship: bool, spec: RulesetSpec) -> str | None:
    if hull is None:
        return None
    if is_flagship and spec.flagship.enabled and spec.flagship.exempt_from_size_limit:
        return codes.HULL_SIZE_FLAG
    return hull.hull_size


def _limit_member_weight(limit: GroupLimit, slot_type: int, hull: HullSpec) -> int | None:
    """Most specific matching member wins: hull, then class, then size."""
    for member in limit.members:
        if member.type_id is not None and member.type_id == slot_type:
            return member.weight
    for member in limit.members:
        if member.ship_class is not None and member.ship_class == hull.ship_class:
            return member.weight
    for member in limit.members:
        if member.hull_size is not None and member.hull_size == hull.hull_size:
            return member.weight
    return None


def evaluate_comp(
    spec: RulesetSpec,
    table: PointTable,
    hulls: HullIndex,
    slots: Sequence[SlotInput],
    bans: Sequence[BanInput] = (),
) -> CompEvaluation:
    violations: list[Violation] = []
    flags: dict[int, list[str]] = defaultdict(list)

    def violate(code: str, severity: str, message: str, slot_nos=(), **data) -> None:
        violations.append(Violation(code, severity, message, tuple(slot_nos), dict(data)))
        for n in slot_nos:
            flags[n].append(code)

    ordered = sorted(slots, key=lambda s: s.slot_no)
    # Slots numbered past the pilot count do not fly: they are reported, then left out of the
    # count, points and every other check.
    over = [s.slot_no for s in ordered if s.slot_no > spec.fielded_pilots]
    if over:
        violate(
            codes.SLOTS_OVER_COUNT,
            codes.SEVERITY_ERROR,
            f"slot(s) {', '.join(map(str, over))} are past this ruleset's "
            f"{spec.fielded_pilots} pilots; clear them in the comp editor",
            over,
            fielded=spec.fielded_pilots,
        )
        ordered = [s for s in ordered if s.slot_no <= spec.fielded_pilots]
    slot_nos = [s.slot_no for s in ordered]
    if len(ordered) != spec.fielded_pilots or slot_nos != list(range(1, spec.fielded_pilots + 1)):
        violate(
            codes.WRONG_SLOT_COUNT,
            codes.SEVERITY_ERROR,
            f"expected slots 1..{spec.fielded_pilots}, got {len(ordered)}",
            expected=spec.fielded_pilots,
            actual=len(ordered),
        )

    # Per-slot lookup
    resolved: dict[int, HullSpec | None] = {}
    base: dict[int, int] = {}
    for slot in ordered:
        if slot.type_id is None:
            resolved[slot.slot_no] = None
            base[slot.slot_no] = 0
            violate(codes.EMPTY_SLOT, codes.SEVERITY_WARNING, "empty slot", [slot.slot_no])
            continue
        hull = hulls.get(slot.type_id)
        resolved[slot.slot_no] = hull
        if hull is None:
            base[slot.slot_no] = 0
            violate(
                codes.UNLISTED_HULL,
                codes.SEVERITY_ERROR,
                f"type {slot.type_id} is not listed in this ruleset",
                [slot.slot_no],
            )
            continue
        points = base_points(hull, table)
        if points is None:
            base[slot.slot_no] = 0
            violate(
                codes.UNLISTED_HULL,
                codes.SEVERITY_ERROR,
                f"{hull.name} has no point value in this table",
                [slot.slot_no],
            )
        else:
            base[slot.slot_no] = points
        if hull.legality == codes.LEGALITY_BANNED:
            violate(
                codes.ILLEGAL_HULL,
                codes.SEVERITY_ERROR,
                f"{hull.name} is banned in this ruleset",
                [slot.slot_no],
            )

    # Flagship
    flag_slots = [s for s in ordered if s.is_flagship]
    if len(flag_slots) > 1:
        violate(
            codes.MULTIPLE_FLAGSHIPS,
            codes.SEVERITY_ERROR,
            "more than one flagship",
            [s.slot_no for s in flag_slots],
        )
    if flag_slots and not spec.flagship.enabled:
        violate(
            codes.FLAGSHIP_DISABLED,
            codes.SEVERITY_ERROR,
            "this ruleset has no flagships",
            [s.slot_no for s in flag_slots],
        )
    for slot in flag_slots:
        hull = resolved.get(slot.slot_no)
        if hull is not None and spec.flagship.enabled and not hull.flagship_eligible:
            violate(
                codes.FLAGSHIP_NOT_ELIGIBLE,
                codes.SEVERITY_ERROR,
                f"{hull.name} cannot be a flagship",
                [slot.slot_no],
            )

    # Copies and inflation
    copy_groups: dict[int, list[int]] = defaultdict(list)
    for slot in ordered:
        hull = resolved.get(slot.slot_no)
        if hull is None:
            continue
        if slot.is_flagship and not spec.flagship.counts_for_inflation:
            continue
        copy_groups[hull.type_id].append(slot.slot_no)
    copy_index: dict[int, int] = {}
    copies_of: dict[int, int] = {}
    for members in copy_groups.values():
        for idx, n in enumerate(members):
            copy_index[n] = idx
            copies_of[n] = len(members)
    inflation: dict[int, int] = {}
    for slot in ordered:
        hull = resolved.get(slot.slot_no)
        if hull is None or not spec.inflation_enabled or slot.slot_no not in copies_of:
            inflation[slot.slot_no] = 0
            continue
        rule = spec.size_rules.get(hull.hull_size or "")
        surcharge = rule.duplicate_surcharge if rule else 0
        inflation[slot.slot_no] = inflation_points(
            copy_index[slot.slot_no], copies_of[slot.slot_no], surcharge, spec.inflation_mode
        )

    # Size limits (effective sizes)
    eff_size: dict[int, str | None] = {}
    by_size: dict[str, list[int]] = defaultdict(list)
    for slot in ordered:
        size = effective_hull_size(resolved.get(slot.slot_no), slot.is_flagship, spec)
        eff_size[slot.slot_no] = size
        if size is not None:
            by_size[size].append(slot.slot_no)
    for size, members in by_size.items():
        rule = spec.size_rules.get(size)
        if rule and rule.max_per_comp is not None and len(members) > rule.max_per_comp:
            violate(
                codes.OVER_SIZE_LIMIT,
                codes.SEVERITY_ERROR,
                f"{len(members)} x {size} exceeds the limit of {rule.max_per_comp}",
                members,
                size=size,
                limit=rule.max_per_comp,
            )

    # Same hull
    if spec.max_same_hull is not None:
        same: dict[int, list[int]] = defaultdict(list)
        for slot in ordered:
            hull = resolved.get(slot.slot_no)
            if hull is None or (slot.is_flagship and not spec.flagship.counts_for_same_hull):
                continue
            same[hull.type_id].append(slot.slot_no)
        for type_id, members in same.items():
            if len(members) > spec.max_same_hull:
                violate(
                    codes.OVER_SAME_HULL,
                    codes.SEVERITY_ERROR,
                    f"{len(members)} x {hulls[type_id].name} exceeds {spec.max_same_hull} of the same hull",
                    members,
                    limit=spec.max_same_hull,
                )

    # Group limits
    for limit in spec.group_limits:
        units = 0
        members_hit: list[int] = []
        for slot in ordered:
            hull = resolved.get(slot.slot_no)
            if hull is None:
                continue
            weight = _limit_member_weight(limit, hull.type_id, hull)
            if weight is not None:
                units += weight
                members_hit.append(slot.slot_no)
        if units > limit.max:
            violate(
                codes.GROUP_LIMIT_EXCEEDED,
                codes.SEVERITY_ERROR,
                limit.message or f"{limit.label}: {units} exceeds max {limit.max}",
                members_hit,
                limit=limit.code,
                units=units,
                max=limit.max,
            )

    # Bans apply to both teams regardless of who made them
    banned_slots: set[int] = set()
    banned_names: list[str] = []
    for slot in ordered:
        hull = resolved.get(slot.slot_no)
        if hull is None:
            continue
        if slot.is_flagship and spec.flagship.enabled and spec.flagship.immune_to_bans:
            continue
        for ban in bans:
            hit = (ban.type_id is not None and ban.type_id == hull.type_id) or (
                ban.ship_class is not None and ban.ship_class == hull.ship_class
            )
            if hit:
                banned_slots.add(slot.slot_no)
                banned_names.append(hull.name)
                break
    if banned_slots:
        violate(
            codes.BANNED,
            codes.SEVERITY_ERROR,
            "banned: " + ", ".join(banned_names),
            sorted(banned_slots),
        )

    # Unique prize hulls
    unique_slots = [s for s in ordered if s.is_unique]
    for slot in unique_slots:
        hull = resolved.get(slot.slot_no)
        if hull is not None and not hull.is_unique:
            violate(
                codes.UNIQUE_NOT_UNIQUE_HULL,
                codes.SEVERITY_WARNING,
                f"{hull.name} is not a unique prize hull in this ruleset",
                [slot.slot_no],
            )
    if unique_slots:
        violate(
            codes.UNIQUE_DECLARED,
            codes.SEVERITY_INFO,
            f"declaring a unique hull grants the opponent {spec.unique_ship_extra_bans} extra bans",
            [s.slot_no for s in unique_slots],
            extra_bans_for_opponent=spec.unique_ship_extra_bans,
        )

    # Assemble slots and totals
    link_counter = 0
    slot_evals: list[SlotEval] = []
    total = 0
    for slot in ordered:
        hull = resolved.get(slot.slot_no)
        link_index = None
        if slot.has_links:
            link_counter += 1
            link_index = link_counter
        points = base[slot.slot_no] + inflation[slot.slot_no]
        total += points
        slot_evals.append(
            SlotEval(
                slot_no=slot.slot_no,
                type_id=slot.type_id,
                name=hull.name if hull else None,
                hull_size=hull.hull_size if hull else None,
                effective_hull_size=eff_size[slot.slot_no],
                base_points=base[slot.slot_no],
                inflation_points=inflation[slot.slot_no],
                total_points=points,
                copy_index=copy_index.get(slot.slot_no, 0),
                copies_of_hull=copies_of.get(slot.slot_no, 1 if hull else 0),
                is_flagship=slot.is_flagship,
                is_banned=slot.slot_no in banned_slots,
                has_links=slot.has_links,
                link_index=link_index,
                flags=tuple(flags[slot.slot_no]),
            )
        )

    if total > spec.point_cap:
        cap_status = codes.CAP_OVER
        violate(
            codes.OVER_CAP,
            codes.SEVERITY_ERROR,
            f"{total} points exceeds the cap of {spec.point_cap}",
            total=total,
            cap=spec.point_cap,
        )
    elif total == spec.point_cap:
        cap_status = codes.CAP_EXACT
    else:
        cap_status = codes.CAP_UNDER
        if total > 0:
            violate(
                codes.UNDER_CAP,
                codes.SEVERITY_INFO,
                f"{spec.point_cap - total} points unspent",
                unspent=spec.point_cap - total,
            )

    is_legal = not any(v.severity == codes.SEVERITY_ERROR for v in violations)
    return CompEvaluation(
        slots=tuple(slot_evals),
        total_points=total,
        point_cap=spec.point_cap,
        cap_status=cap_status,
        unspent_points=max(spec.point_cap - total, 0),
        violations=tuple(violations),
        is_legal=is_legal,
        point_table_version_id=table.version_id,
    )
