"""The one place access is decided. Roles are rows with a permission set; endpoints ask for codes."""

import contextlib

from ninja.errors import HttpError

from .models import Membership, MembershipStatus

# code -> (group, label, description). The Roles page renders this; the migration seeds from it.
PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "view_scrims": ("Scrims", "View all scrims", "See every scrim, its page, history and CSV."),
    "view_assigned_scrims": (
        "Scrims",
        "View assigned scrims",
        "See only the scrims this member is fielded in.",
    ),
    "rsvp": ("Scrims", "RSVP", "Answer attending, unable or maybe on scrims they can see."),
    "fly": ("Scrims", "Fly", "On the roster: can be put in a lineup and edits their own slot."),
    "score": ("Scrims", "Score", "Toggle deaths and set round outcomes."),
    "edit_sets": ("Scrims", "Edit sets", "Bans, comp load, lineups, set fields and rounds."),
    "manage_scrims": (
        "Scrims",
        "Manage scrims",
        "Create, edit and archive scrims; attendance; roster and opponents; share links.",
    ),
    "browse_library": (
        "Library",
        "Browse library",
        "Read comps and fits, rulesets, ships, points and the scratchpad.",
    ),
    "suggest_library": (
        "Library",
        "Suggest",
        "Create comps and fits as suggestions and edit their own suggestions.",
    ),
    "manage_library": (
        "Library",
        "Manage library",
        "Change statuses, edit any comp or fit, manage archetypes.",
    ),
    "manage_members": (
        "Team",
        "Manage members",
        "Members, invites and admission rules; assign any role except admin.",
    ),
    "view_audit": ("Team", "View audit log", "Read the team audit log."),
    "view_pilot_notes": ("Team", "View pilot notes", "Read leadership notes on pilots."),
    "manage_team": ("Team", "Manage team", "Team settings, the season and the roles themselves."),
}
PERMISSION_CODES: frozenset[str] = frozenset(PERMISSIONS)

# The leadership flag on a member adds these on top of the role.
LEADERSHIP_PERMISSIONS: frozenset[str] = frozenset({"view_audit", "view_pilot_notes"})

_CACHE_ATTR = "_attool_permissions"


def active_membership(user) -> Membership | None:
    if not getattr(user, "is_authenticated", False):
        return None
    membership = getattr(user, "membership", None)
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        return None
    return membership


def permissions_for(user) -> frozenset[str]:
    """The member's effective permission set, computed once per request user object."""
    cached = getattr(user, _CACHE_ATTR, None)
    if cached is not None:
        return cached
    membership = active_membership(user)
    if membership is None:
        result: frozenset[str] = frozenset()
    elif membership.role.is_system:
        result = PERMISSION_CODES
    else:
        result = frozenset(membership.role.permissions)
        if membership.is_leadership:
            result = result | LEADERSHIP_PERMISSIONS
    with contextlib.suppress(AttributeError):
        setattr(user, _CACHE_ATTR, result)
    return result


def has_perm(user, code: str) -> bool:
    return code in permissions_for(user)


def require_perm(user, code: str, message: str | None = None) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not has_perm(user, code):
        raise HttpError(403, message or f"requires the {PERMISSIONS[code][1].lower()} permission")


def is_admin(user) -> bool:
    membership = active_membership(user)
    return membership is not None and membership.role.is_system


def is_member(user) -> bool:
    return active_membership(user) is not None


def require_member(user) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not is_member(user):
        raise HttpError(403, "requires an active membership")


# Named helpers kept for readability at the call sites.


def is_leadership(user) -> bool:
    return has_perm(user, "view_audit")


def require_leadership(user) -> None:
    require_perm(user, "view_audit", "requires the audit log permission or the leadership flag")


def can_manage_members(user) -> bool:
    return has_perm(user, "manage_members")


def can_assign_role(actor, role) -> bool:
    """Members with manage_members grant any role; the admin role only comes from an admin."""
    if not has_perm(actor, "manage_members"):
        return False
    return not role.is_system or is_admin(actor)


def can_browse_library(user) -> bool:
    return has_perm(user, "browse_library")


def require_browse_library(user) -> None:
    require_perm(user, "browse_library", "library browsing is not enabled for your role")


def can_suggest_library(user) -> bool:
    return has_perm(user, "suggest_library")


def can_manage_library(user) -> bool:
    return has_perm(user, "manage_library")


def can_manage_scrims(user) -> bool:
    return has_perm(user, "manage_scrims")


def require_manage_scrims(user) -> None:
    require_perm(user, "manage_scrims", "requires the manage scrims permission")


def can_score(user) -> bool:
    return has_perm(user, "score")


def require_score(user) -> None:
    require_perm(user, "score", "scoring is not enabled for your role")


def can_browse_scrims(user) -> bool:
    return has_perm(user, "view_scrims") or has_perm(user, "view_assigned_scrims")


def require_scrim_access(user) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_browse_scrims(user):
        raise HttpError(403, "scrims are visible to team members")


def can_rsvp(user) -> bool:
    return has_perm(user, "rsvp")


def require_rsvp(user) -> None:
    require_perm(user, "rsvp", "your role cannot RSVP")


def can_fly(user) -> bool:
    return has_perm(user, "fly")


def can_edit_sets(user) -> bool:
    return has_perm(user, "edit_sets")


def require_edit_sets(user) -> None:
    require_perm(user, "edit_sets", "requires the edit sets permission")


def can_view_session(user, session) -> bool:
    """`view_scrims` sees everything; `view_assigned_scrims` only where a linked pilot is fielded."""
    if has_perm(user, "view_scrims"):
        return True
    if not has_perm(user, "view_assigned_scrims"):
        return False
    from apps.scrims.models import Assignment

    return Assignment.objects.filter(round__set__session=session, pilot__user=user).exists()


def require_view_session(user, session) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_view_session(user, session):
        raise HttpError(403, "you are not on this scrim")
