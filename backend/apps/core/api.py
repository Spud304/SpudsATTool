from datetime import datetime

from django.conf import settings
from django.db import connection
from django.http import HttpRequest
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.audit.services import record
from apps.rules import selection
from apps.rules.models import Ruleset
from apps.sde.health import latest_build_summary

from .models import Team

router = Router(tags=["core"])


class HealthOut(Schema):
    status: str
    version: str
    database: str
    sde_build: int | None = None
    sde_release_date: datetime | None = None
    sde_imported_at: datetime | None = None
    sde_stale: bool = True


class TeamOut(Schema):
    id: int
    name: str
    slug: str
    alliance_id: int | None
    affiliation_grace_hours: int
    active_ruleset: str | None
    active_ruleset_is_fallback: bool


class TeamPatch(Schema):
    name: str | None = None
    alliance_id: int | None = None
    affiliation_grace_hours: int | None = None
    active_ruleset: str | None = None  # tournament code


def team_out(team: Team) -> dict:
    active = selection.active_ruleset(team)
    return {
        "id": team.pk,
        "name": team.name,
        "slug": team.slug,
        "alliance_id": team.alliance_id,
        "affiliation_grace_hours": team.affiliation_grace_hours,
        "active_ruleset": active.code if active else None,
        "active_ruleset_is_fallback": team.active_ruleset_id is None,
    }


@router.get("/health", auth=None, response=HealthOut)
def health(request: HttpRequest):
    database = "ok"
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:  # pragma: no cover - only on a broken deployment
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": settings.APP_VERSION,
        "database": database,
        **latest_build_summary(),
    }


@router.get("/team", response=TeamOut)
def get_team(request: HttpRequest):
    permissions.require_member(request.user)
    return team_out(Team.get_solo())


@router.patch("/team", response=TeamOut)
def patch_team(request: HttpRequest, payload: TeamPatch):
    permissions.require_perm(request.user, "manage_team")
    team = Team.get_solo()
    changes = payload.dict(exclude_unset=True)
    before = {k: getattr(team, k) for k in changes if k != "active_ruleset"}
    if "active_ruleset" in changes:
        code = changes["active_ruleset"]
        current = team.active_ruleset
        before["active_ruleset"] = current.code if current else None
        if code is None:
            team.active_ruleset = None
        else:
            ruleset = (
                Ruleset.objects.select_related("tournament").filter(tournament__code=code).first()
            )
            if ruleset is None:
                raise HttpError(422, f"unknown ruleset {code!r}")
            team.active_ruleset = ruleset
    for field, value in changes.items():
        if field != "active_ruleset":
            setattr(team, field, value)
    team.save()
    record(actor=request.user, action="team.updated", target=team, before=before, after=changes)
    return team_out(team)
