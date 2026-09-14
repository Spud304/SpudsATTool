"""Which ruleset the team is working in this season. Admin-set on Team, with a sensible fallback."""

from apps.core.models import Team

from .models import Ruleset, TablePurpose


def _with_tournament():
    return Ruleset.objects.select_related("tournament")


def fallback_ruleset() -> Ruleset | None:
    """Newest ruleset that has a current cost table, else the newest ruleset at all."""
    scored = (
        _with_tournament()
        .filter(point_versions__purpose=TablePurpose.COST, point_versions__is_current=True)
        .order_by("-tournament__year", "tournament__code")
        .first()
    )
    return scored or _with_tournament().order_by("-tournament__year", "tournament__code").first()


def active_ruleset(team: Team | None = None) -> Ruleset | None:
    team = team or Team.get_solo()
    if team.active_ruleset_id is not None:
        found = _with_tournament().filter(pk=team.active_ruleset_id).first()
        if found is not None:
            return found
    return fallback_ruleset()


def set_active_if_unset(ruleset: Ruleset) -> bool:
    team = Team.get_solo()
    if team.active_ruleset_id is not None:
        return False
    team.active_ruleset = ruleset
    team.save(update_fields=["active_ruleset"])
    return True
