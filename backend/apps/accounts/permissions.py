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
