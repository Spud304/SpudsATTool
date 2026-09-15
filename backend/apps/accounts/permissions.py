"""The one place role capabilities are decided. API endpoints call these helpers."""

from ninja.errors import HttpError

from .models import ROLE_RANK, Membership, MembershipStatus, Role


def active_membership(user) -> Membership | None:
    if not getattr(user, "is_authenticated", False):
        return None
    membership = getattr(user, "membership", None)
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        return None
    return membership


def has_role(user, minimum: Role) -> bool:
    membership = active_membership(user)
    if membership is None:
        return False
    if membership.role == Role.GUEST:
        return minimum in (Role.GUEST, Role.VIEWER)
    return ROLE_RANK[Role(membership.role)] >= ROLE_RANK[minimum]


def require_role(user, minimum: Role) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not has_role(user, minimum):
        raise HttpError(403, f"requires role {minimum} or higher")


def is_leadership(user) -> bool:
    membership = active_membership(user)
    if membership is None:
        return False
    return membership.is_leadership or ROLE_RANK[Role(membership.role)] >= ROLE_RANK[Role.CAPTAIN]


def require_leadership(user) -> None:
    if not is_leadership(user):
        raise HttpError(403, "requires captain, admin, or the leadership flag")


def can_manage_members(user) -> bool:
    return has_role(user, Role.CAPTAIN)


def can_assign_role(actor, role: str) -> bool:
    """Only admins may grant admin; captains may grant anything below."""
    if role == Role.ADMIN:
        return has_role(actor, Role.ADMIN)
    return has_role(actor, Role.CAPTAIN)


def can_browse_library(user) -> bool:
    """Theorycrafters and above always; pilots when the team allows it."""
    from apps.core.models import Team

    if has_role(user, Role.THEORYCRAFTER):
        return True
    return has_role(user, Role.PILOT) and Team.get_solo().pilots_can_browse_library


def require_browse_library(user) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_browse_library(user):
        raise HttpError(403, "library browsing is not enabled for your role")


def can_manage_library(user) -> bool:
    return has_role(user, Role.THEORYCRAFTER)


def can_manage_scrims(user) -> bool:
    return has_role(user, Role.CAPTAIN)


def require_manage_scrims(user) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_manage_scrims(user):
        raise HttpError(403, "requires captain or admin")


def can_score(user) -> bool:
    """Toggling deaths and outcomes: theorycrafters always, pilots when the team allows it."""
    from apps.core.models import Team

    if has_role(user, Role.THEORYCRAFTER):
        return True
    return has_role(user, Role.PILOT) and Team.get_solo().pilots_can_score


def can_browse_scrims(user) -> bool:
    """Any active member except guests (guests get assigned sessions in a later slice)."""
    membership = active_membership(user)
    return membership is not None and membership.role != Role.GUEST


def require_scrim_access(user) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_browse_scrims(user):
        raise HttpError(403, "scrims are visible to team members")


def can_edit_sets(user) -> bool:
    """Bans, comps, lineups and set fields: theorycrafters and up."""
    return has_role(user, Role.THEORYCRAFTER)


def require_edit_sets(user) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_edit_sets(user):
        raise HttpError(403, "requires theorycrafter, captain or admin")


def require_score(user) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_score(user):
        raise HttpError(403, "scoring is off for pilots on this team")


def can_view_session(user, session) -> bool:
    """Members read every scrim; guests only the ones a pilot linked to them is assigned in."""
    membership = active_membership(user)
    if membership is None:
        return False
    if membership.role != Role.GUEST:
        return True
    from apps.scrims.models import Assignment

    return Assignment.objects.filter(round__set__session=session, pilot__user=user).exists()


def require_view_session(user, session) -> None:
    if not getattr(user, "is_authenticated", False):
        raise HttpError(401, "login required")
    if not can_view_session(user, session):
        raise HttpError(403, "you are not on this scrim")
