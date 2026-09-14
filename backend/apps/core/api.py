from datetime import datetime

from django.conf import settings
from django.db import connection
from django.http import HttpRequest
from ninja import Router, Schema

from apps.accounts.models import Role
from apps.accounts.permissions import require_role
from apps.audit.services import record
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
    pilots_can_score: bool
    pilots_can_browse_library: bool
    affiliation_grace_hours: int


class TeamPatch(Schema):
    name: str | None = None
    alliance_id: int | None = None
    pilots_can_score: bool | None = None
    pilots_can_browse_library: bool | None = None
    affiliation_grace_hours: int | None = None


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
    require_role(request.user, Role.PILOT)
    return Team.get_solo()


@router.patch("/team", response=TeamOut)
def patch_team(request: HttpRequest, payload: TeamPatch):
    require_role(request.user, Role.ADMIN)
    team = Team.get_solo()
    changes = payload.dict(exclude_unset=True)
    before = {k: getattr(team, k) for k in changes}
    for field, value in changes.items():
        setattr(team, field, value)
    team.save()
    record(actor=request.user, action="team.updated", target=team, before=before, after=changes)
    return team
