"""The comp scratchpad's saved state at /api/scratchpad: one private document per member."""

from typing import cast

from django.http import HttpRequest
from ninja import Router, Schema

from apps.accounts import permissions
from apps.accounts.models import Role, User
from apps.rules import selection
from apps.rules.models import Ruleset

from .models import Scratchpad

router = Router(tags=["library"])


class ScratchSlotIn(Schema):
    type_id: int | None = None
    is_flagship: bool = False
    has_links: bool = False


class ScratchpadIn(Schema):
    ruleset: str | None = None
    slots: list[ScratchSlotIn]
    bans: list[int] = []


class ScratchpadOut(Schema):
    ruleset: str | None
    slots: list[ScratchSlotIn]
    bans: list[int]
    updated_at: str | None


def _out(row: Scratchpad | None) -> dict:
    if row is None:
        active = selection.active_ruleset()
        return {
            "ruleset": active.code if active else None,
            "slots": [],
            "bans": [],
            "updated_at": None,
        }
    return {
        "ruleset": row.ruleset.tournament.code if row.ruleset else None,
        "slots": row.slots,
        "bans": row.bans,
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("", response=ScratchpadOut)
def get_scratchpad(request: HttpRequest):
    permissions.require_role(request.user, Role.PILOT)
    row = Scratchpad.objects.filter(user=request.user).select_related("ruleset__tournament").first()
    return _out(row)


@router.put("", response=ScratchpadOut)
def put_scratchpad(request: HttpRequest, payload: ScratchpadIn):
    permissions.require_role(request.user, Role.PILOT)
    user = cast(User, request.user)
    ruleset = (
        Ruleset.objects.filter(tournament__code=payload.ruleset).first()
        if payload.ruleset
        else None
    )
    row, _ = Scratchpad.objects.update_or_create(
        user=user,
        defaults={
            "ruleset": ruleset,
            "slots": [s.dict() for s in payload.slots],
            "bans": payload.bans,
        },
    )
    row.ruleset = ruleset
    return _out(row)
