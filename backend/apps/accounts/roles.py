"""Team roles as data: the seeded defaults, lookups, and the admin's create, update and delete."""

from enum import Enum

from django.db import transaction
from django.utils.text import slugify
from ninja.errors import HttpError

from apps.audit.services import record

from .models import AdmissionRule, Invite, Membership, Role, TeamRole
from .permissions import PERMISSION_CODES

ADMIN_SLUG = Role.ADMIN


def default_definitions(
    *, pilots_can_score: bool = True, pilots_can_browse: bool = True
) -> list[dict]:
    """The six roles the app shipped with, as permission sets. The pilot role takes the old team toggles."""
    pilot = ["view_scrims", "rsvp", "fly", "suggest_library"]
    if pilots_can_score:
        pilot.append("score")
    if pilots_can_browse:
        pilot.append("browse_library")
    return [
        {
            "slug": Role.ADMIN,
            "name": "Admin",
            "is_system": True,
            "sort_order": 0,
            "permissions": sorted(PERMISSION_CODES),
            "description": "Everything, always. Cannot be changed.",
        },
        {
            "slug": Role.CAPTAIN,
            "name": "Captain",
            "sort_order": 1,
            "permissions": [
                "view_scrims",
                "rsvp",
                "fly",
                "score",
                "edit_sets",
                "manage_scrims",
                "browse_library",
                "suggest_library",
                "manage_library",
                "manage_members",
                "view_audit",
                "view_pilot_notes",
            ],
            "description": "Runs scrim nights and the roster.",
        },
        {
            "slug": Role.THEORYCRAFTER,
            "name": "Theorycrafter",
            "sort_order": 2,
            "permissions": [
                "view_scrims",
                "rsvp",
                "fly",
                "score",
                "edit_sets",
                "browse_library",
                "suggest_library",
                "manage_library",
            ],
            "description": "Owns comps and fits; edits any scrim set.",
        },
        {
            "slug": Role.PILOT,
            "name": "Pilot",
            "sort_order": 3,
            "permissions": pilot,
            "description": "Flies, RSVPs, suggests comps and fits.",
        },
        {
            "slug": Role.GUEST,
            "name": "Guest",
            "sort_order": 4,
            "permissions": ["view_assigned_scrims", "fly"],
            "description": "Sees only the scrims they are fielded in.",
        },
        {
            "slug": Role.VIEWER,
            "name": "Viewer",
            "sort_order": 5,
            "permissions": ["view_scrims"],
            "description": "Read-only.",
        },
    ]


def seed_defaults(TeamRoleModel=TeamRole, **toggles) -> None:
    """Create any default role that is missing. Safe to repeat; existing rows are left alone."""
    for definition in default_definitions(**toggles):
        TeamRoleModel.objects.get_or_create(
            slug=definition["slug"], defaults={k: v for k, v in definition.items() if k != "slug"}
        )


def by_slug(role) -> TeamRole:
    """Accepts a slug or a TeamRole; unknown slugs are a 422 (or ValueError outside a request)."""
    if isinstance(role, TeamRole):
        return role
    slug = (
        role.value if isinstance(role, Enum) else str(role)
    )  # str(Role.CAPTAIN) is "Role.CAPTAIN"
    found = TeamRole.objects.filter(slug=slug).first()
    if found is None and not TeamRole.objects.exists():
        # A flushed table (transactional tests) or a database created without the data migration.
        seed_defaults()
        found = TeamRole.objects.filter(slug=slug).first()
    if found is None:
        raise HttpError(422, f"unknown role {slug!r}")
    return found


def admin_role() -> TeamRole:
    return TeamRole.objects.get(slug=ADMIN_SLUG)


def validate_permissions(codes: list[str]) -> list[str]:
    unknown = sorted(set(codes) - PERMISSION_CODES)
    if unknown:
        raise HttpError(422, f"unknown permissions: {', '.join(unknown)}")
    return sorted(set(codes))


def _unique_slug(name: str) -> str:
    base = slugify(name)[:40] or "role"
    slug = base
    n = 2
    while TeamRole.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def create_role(actor, *, name: str, description: str = "", permissions: list[str]) -> TeamRole:
    name = name.strip()
    if not name:
        raise HttpError(422, "a role needs a name")
    if TeamRole.objects.filter(name__iexact=name).exists():
        raise HttpError(409, "a role with that name already exists")
    codes = validate_permissions(permissions)
    last = TeamRole.objects.order_by("-sort_order").first()
    role = TeamRole.objects.create(
        slug=_unique_slug(name),
        name=name,
        description=description.strip(),
        permissions=codes,
        sort_order=(last.sort_order + 1) if last else 0,
    )
    record(actor=actor, action="role.created", target=role, after={"permissions": codes})
    return role


def update_role(actor, role: TeamRole, *, reason: str = "", **changes) -> TeamRole:
    before = {}
    if "permissions" in changes:
        if role.is_system:
            raise HttpError(409, "the admin role always holds every permission")
        changes["permissions"] = validate_permissions(changes["permissions"])
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise HttpError(422, "a role needs a name")
        if TeamRole.objects.filter(name__iexact=changes["name"]).exclude(pk=role.pk).exists():
            raise HttpError(409, "a role with that name already exists")
    for field, value in changes.items():
        before[field] = getattr(role, field)
        setattr(role, field, value)
    with transaction.atomic():
        role.save()
        if (
            "permissions" in changes
            and "fly" in changes["permissions"]
            and "fly" not in before["permissions"]
        ):
            from apps.scrims.roster import ensure_pilot_for

            for membership in Membership.objects.filter(role=role, status="active").select_related(
                "user"
            ):
                ensure_pilot_for(membership.user)
    record(
        actor=actor, action="role.updated", target=role, reason=reason, before=before, after=changes
    )
    return role


def in_use(role: TeamRole) -> dict[str, int]:
    return {
        "members": Membership.objects.filter(role=role).count(),
        "invites": Invite.objects.filter(role=role).count(),
        "rules": AdmissionRule.objects.filter(default_role=role).count(),
    }


def delete_role(
    actor, role: TeamRole, *, reassign_to: TeamRole | None = None, reason: str = ""
) -> None:
    if role.is_system:
        raise HttpError(409, "the admin role cannot be deleted")
    usage = in_use(role)
    if any(usage.values()):
        if reassign_to is None:
            raise HttpError(409, "the role is in use; pass reassign_to")
        if reassign_to.pk == role.pk:
            raise HttpError(422, "reassign_to must be a different role")
    with transaction.atomic():
        if reassign_to is not None:
            Membership.objects.filter(role=role).update(role=reassign_to)
            Invite.objects.filter(role=role).update(role=reassign_to)
            AdmissionRule.objects.filter(default_role=role).update(default_role=reassign_to)
        record(
            actor=actor,
            action="role.deleted",
            target=role,
            reason=reason,
            before={
                "permissions": role.permissions,
                "reassigned_to": reassign_to.slug if reassign_to else None,
                **usage,
            },
        )
        role.delete()
