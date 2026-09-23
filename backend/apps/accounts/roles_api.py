"""Roles at /api/team/roles: the permission catalogue, the roles, and the admin's edits."""

from typing import Any, cast

from django.db.models import Count, Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema

from . import permissions, roles
from .models import TeamRole, User

router = Router(tags=["accounts"])


class PermissionOut(Schema):
    code: str
    group: str
    label: str
    description: str


class RoleOut(Schema):
    id: int
    slug: str
    name: str
    description: str
    permissions: list[str]
    is_system: bool
    member_count: int


class RolesOut(Schema):
    roles: list[RoleOut]
    catalog: list[PermissionOut]


class RoleIn(Schema):
    name: str = Field(max_length=60)
    description: str = Field("", max_length=200)
    permissions: list[str] = []


class RolePatch(Schema):
    name: str | None = Field(None, max_length=60)
    description: str | None = Field(None, max_length=200)
    permissions: list[str] | None = None
    reason: str = ""


def _role_out(role: TeamRole, member_count: int | None = None) -> dict:
    if member_count is None:
        member_count = role.memberships.filter(status="active").count()
    return {
        "id": role.pk,
        "slug": role.slug,
        "name": role.name,
        "description": role.description,
        "permissions": sorted(permissions.PERMISSION_CODES) if role.is_system else role.permissions,
        "is_system": role.is_system,
        "member_count": member_count,
    }


def _catalog() -> list[dict]:
    return [
        {"code": code, "group": group, "label": label, "description": description}
        for code, (group, label, description) in permissions.PERMISSIONS.items()
    ]


@router.get("", response=RolesOut)
def list_roles(request: HttpRequest):
    permissions.require_member(request.user)
    qs = TeamRole.objects.annotate(
        active_members=Count("memberships", filter=Q(memberships__status="active"))
    ).order_by("sort_order", "name")
    return {
        "roles": [_role_out(r, cast(Any, r).active_members) for r in qs],
        "catalog": _catalog(),
    }


@router.post("", response={201: RoleOut})
def create_role(request: HttpRequest, payload: RoleIn):
    permissions.require_perm(request.user, "manage_team")
    role = roles.create_role(
        cast(User, request.user),
        name=payload.name,
        description=payload.description,
        permissions=payload.permissions,
    )
    return 201, _role_out(role, 0)


@router.patch("/{role_id}", response=RoleOut)
def patch_role(request: HttpRequest, role_id: int, payload: RolePatch):
    permissions.require_perm(request.user, "manage_team")
    role = get_object_or_404(TeamRole, pk=role_id)
    changes = payload.dict(exclude_unset=True, exclude={"reason"})
    role = roles.update_role(cast(User, request.user), role, reason=payload.reason, **changes)
    return _role_out(role)


@router.delete("/{role_id}", response={204: None})
def delete_role(
    request: HttpRequest, role_id: int, reassign_to: int | None = None, reason: str = ""
):
    permissions.require_perm(request.user, "manage_team")
    role = get_object_or_404(TeamRole, pk=role_id)
    target = get_object_or_404(TeamRole, pk=reassign_to) if reassign_to is not None else None
    roles.delete_role(cast(User, request.user), role, reassign_to=target, reason=reason)
    return 204, None
