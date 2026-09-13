"""Read-only rules endpoints for the comp scratchpad. Open in DEBUG only until EVE SSO lands."""

from dataclasses import asdict

from django.conf import settings
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from . import adapters
from .engine import BanInput, SlotInput, evaluate_comp
from .engine.comp import base_points
from .models import Ruleset


def debug_only(request: HttpRequest):
    """Temporary gate: these endpoints have no auth yet, so they only answer in DEBUG."""
    return True if settings.DEBUG else None


router = Router(tags=["rules"], auth=debug_only)


class HullSizeOut(Schema):
    size: str
    label: str
    max_per_comp: int | None
    duplicate_surcharge: int


class RulesetOut(Schema):
    code: str
    name: str
    verified: bool
    fielded_pilots: int
    point_cap: int
    max_same_hull: int | None
    inflation_enabled: bool
    inflation_mode: str
    flagship_enabled: bool
    has_point_table: bool
    hull_sizes: list[HullSizeOut]


class ShipOut(Schema):
    type_id: int
    name: str
    ship_class: str | None
    hull_size: str | None
    points: int | None
    legality: str
    flagship_eligible: bool
    is_unique: bool


class SlotIn(Schema):
    slot_no: int
    type_id: int | None = None
    is_flagship: bool = False
    is_unique: bool = False
    has_links: bool = False


class BanIn(Schema):
    type_id: int | None = None
    ship_class: str | None = None
    made_by_side: str = "A"


class EvaluateIn(Schema):
    slots: list[SlotIn]
    bans: list[BanIn] = []


class ViolationOut(Schema):
    code: str
    severity: str
    message: str
    slot_nos: list[int]
    data: dict[str, int | str]


class SlotEvalOut(Schema):
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
    flags: list[str]


class EvaluateOut(Schema):
    slots: list[SlotEvalOut]
    total_points: int
    point_cap: int
    cap_status: str
    unspent_points: int
    violations: list[ViolationOut]
    is_legal: bool
    point_table_version_id: int


def _ruleset(code: str) -> Ruleset:
    return get_object_or_404(
        Ruleset.objects.select_related("tournament").prefetch_related("hull_sizes"),
        tournament__code=code,
    )


def _inputs(ruleset: Ruleset) -> adapters.EngineInputs:
    try:
        return adapters.engine_inputs_for(ruleset)
    except adapters.NoPointTable as exc:
        raise HttpError(409, str(exc)) from exc


@router.get("", response=list[RulesetOut])
def list_rulesets(request: HttpRequest):
    out = []
    for rs in Ruleset.objects.select_related("tournament").prefetch_related(
        "hull_sizes", "point_versions"
    ):
        out.append(
            {
                "code": rs.code,
                "name": rs.tournament.name,
                "verified": rs.tournament.verified,
                "fielded_pilots": rs.fielded_pilots,
                "point_cap": rs.point_cap,
                "max_same_hull": rs.max_same_hull,
                "inflation_enabled": rs.duplicate_inflation_enabled,
                "inflation_mode": rs.duplicate_inflation_mode,
                "flagship_enabled": rs.flagship_enabled,
                "has_point_table": any(
                    v.is_current and v.purpose == "cost" for v in rs.point_versions.all()
                ),
                "hull_sizes": [
                    {
                        "size": h.hull_size,
                        "label": h.label,
                        "max_per_comp": h.max_per_comp,
                        "duplicate_surcharge": h.duplicate_surcharge,
                    }
                    for h in rs.hull_sizes.all()
                ],
            }
        )
    return out


@router.get("/{code}/ships", response=list[ShipOut])
def list_ships(request: HttpRequest, code: str):
    inputs = _inputs(_ruleset(code))
    return [
        {
            "type_id": h.type_id,
            "name": h.name,
            "ship_class": h.ship_class,
            "hull_size": h.hull_size,
            "points": base_points(h, inputs.table),
            "legality": h.legality,
            "flagship_eligible": h.flagship_eligible,
            "is_unique": h.is_unique,
        }
        for h in sorted(inputs.hulls.values(), key=lambda h: h.name)
    ]


@router.post("/{code}/evaluate", response=EvaluateOut)
def evaluate(request: HttpRequest, code: str, payload: EvaluateIn):
    inputs = _inputs(_ruleset(code))
    slots = [SlotInput(**s.dict()) for s in payload.slots]
    bans = [BanInput(**b.dict()) for b in payload.bans]
    result = evaluate_comp(inputs.spec, inputs.table, inputs.hulls, slots, bans)
    return asdict(result)
