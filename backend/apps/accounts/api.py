from datetime import datetime, timedelta
from typing import cast

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.audit.services import record
from apps.core.models import Team
from apps.rules import selection

from . import permissions, roles
from .models import (
    AdmissionRule,
    AdmissionRuleKind,
    EveCharacter,
    Invite,
    Membership,
    MembershipSource,
    MembershipStatus,
    TeamRole,
    User,
)

router = Router(tags=["accounts"])


class CharacterOut(Schema):
    character_id: int
    name: str
    corporation_id: int | None
    alliance_id: int | None
    is_main: bool = False


class MembershipOut(Schema):
    role: str
    role_name: str
    status: str
    source: str
    is_leadership: bool


class TeamBrief(Schema):
    name: str
    active_ruleset: str | None = None


class Capabilities(Schema):
    """One boolean per permission code in permissions.PERMISSIONS, plus is_admin."""

    is_admin: bool
    view_scrims: bool
    view_assigned_scrims: bool
    rsvp: bool
    fly: bool
    score: bool
    edit_sets: bool
    manage_scrims: bool
    browse_library: bool
    suggest_library: bool
    manage_library: bool
    manage_members: bool
    view_audit: bool
    view_pilot_notes: bool
    manage_team: bool


class MeOut(Schema):
    authenticated: bool
    user_id: int | None = None
    display_name: str | None = None
    characters: list[CharacterOut] = []
    membership: MembershipOut | None = None
    team: TeamBrief | None = None
    capabilities: Capabilities | None = None
    sso_configured: bool = True
    admins_configured: bool = True
    version: str = ""


class MemberOut(Schema):
    user_id: int
    display_name: str
    role: str
    role_name: str
    status: str
    source: str
    is_leadership: bool
    note: str
    characters: list[CharacterOut]
    created_at: datetime


class MemberPatch(Schema):
    role: str | None = None
    is_leadership: bool | None = None
    status: MembershipStatus | None = None
    note: str | None = None
    reason: str = ""


class RemoveIn(Schema):
    reason: str = ""


class InviteOut(Schema):
    id: int
    token: str
    url: str
    role: str
    role_name: str
    uses_left: int
    expires_at: datetime
    note: str
    created_at: datetime


class InviteIn(Schema):
    role: str = "pilot"
    uses: int = 1
    expires_in_hours: int = 72
    note: str = ""


class AdmissionRuleOut(Schema):
    id: int
    kind: str
    entity_id: int
    entity_name: str
    default_role: str
    default_role_name: str
    enabled: bool
    created_at: datetime


class AdmissionRuleIn(Schema):
    kind: AdmissionRuleKind
    entity_id: int
    entity_name: str = ""
    default_role: str = "pilot"
    enabled: bool = True


class AdmissionRulePatch(Schema):
    entity_name: str | None = None
    default_role: str | None = None
    enabled: bool | None = None


class MainCharacterIn(Schema):
    character_id: int


def _characters(user: User) -> list[dict]:
    return [
        {
            "character_id": c.character_id,
            "name": c.name,
            "corporation_id": c.corporation_id,
            "alliance_id": c.alliance_id,
            "is_main": user.main_character_id == c.character_id,
        }
        for c in user.characters.all()
    ]


def _member_out(membership: Membership) -> dict:
    user = membership.user
    return {
        "user_id": user.pk,
        "display_name": user.display_name,
        "role": membership.role.slug,
        "role_name": membership.role.name,
        "status": membership.status,
        "source": membership.source,
        "is_leadership": membership.is_leadership,
        "note": membership.note,
        "characters": _characters(user),
        "created_at": membership.created_at,
    }


def _capabilities(user) -> dict:
    granted = permissions.permissions_for(user)
    out = {code: code in granted for code in permissions.PERMISSIONS}
    out["is_admin"] = permissions.is_admin(user)
    return out


def _membership_out(membership: Membership) -> dict:
    return {
        "role": membership.role.slug,
        "role_name": membership.role.name,
        "status": membership.status,
        "source": membership.source,
        "is_leadership": membership.is_leadership,
    }


def _rule_out(rule: AdmissionRule) -> dict:
    return {
        "id": rule.pk,
        "kind": rule.kind,
        "entity_id": rule.entity_id,
        "entity_name": rule.entity_name,
        "default_role": rule.default_role.slug,
        "default_role_name": rule.default_role.name,
        "enabled": rule.enabled,
        "created_at": rule.created_at,
    }


def _invite_out(request: HttpRequest, invite: Invite) -> dict:
    return {
        "id": invite.pk,
        "token": invite.token,
        "url": request.build_absolute_uri(f"/auth/join/{invite.token}"),
        "role": invite.role.slug,
        "role_name": invite.role.name,
        "uses_left": invite.uses_left,
        "expires_at": invite.expires_at,
        "note": invite.note,
        "created_at": invite.created_at,
    }


def _require_manager(user) -> None:
    if not user.is_authenticated:
        raise HttpError(401, "login required")
    if not permissions.can_manage_members(user):
        raise HttpError(403, "requires the manage members permission")


@router.get("/me", auth=None, response=MeOut)
def me(request: HttpRequest):
    base = {
        "sso_configured": bool(settings.EVE_CLIENT_ID),
        "admins_configured": bool(settings.ADMIN_CHARACTER_IDS),
        "version": settings.APP_VERSION,
    }
    if not request.user.is_authenticated:
        return {"authenticated": False, **base}
    user = cast(User, request.user)
    team = Team.get_solo()
    membership = permissions.active_membership(user)
    return {
        "authenticated": True,
        "user_id": user.pk,
        "display_name": user.display_name,
        "characters": _characters(user),
        "membership": _membership_out(membership) if membership else None,
        "team": {
            "name": team.name,
            "active_ruleset": active.code if (active := selection.active_ruleset(team)) else None,
        },
        "capabilities": _capabilities(user) if membership else None,
        **base,
    }


@router.post("/me/main-character", response=MeOut)
def set_main_character(request: HttpRequest, payload: MainCharacterIn):
    user = cast(User, request.user)
    character = get_object_or_404(EveCharacter, character_id=payload.character_id, user=user)
    user.main_character = character
    user.display_name = character.name
    user.save(update_fields=["main_character", "display_name"])
    return me(request)


@router.get("/team/members", response=list[MemberOut])
def list_members(request: HttpRequest):
    permissions.require_member(request.user)
    qs = Membership.objects.select_related("user", "role").prefetch_related("user__characters")
    return [_member_out(m) for m in qs.order_by("user__display_name")]


def _guard_last_admin(membership: Membership, changes: dict) -> None:
    new_role = changes.get("role")
    losing_admin = membership.role.is_system and (
        (new_role is not None and not new_role.is_system)
        or changes.get("status") not in (None, MembershipStatus.ACTIVE)
    )
    if losing_admin:
        others = Membership.objects.filter(
            role__is_system=True, status=MembershipStatus.ACTIVE
        ).exclude(pk=membership.pk)
        if not others.exists():
            raise HttpError(409, "cannot demote or remove the last active admin")


@router.patch("/team/members/{user_id}", response=MemberOut)
def patch_member(request: HttpRequest, user_id: int, payload: MemberPatch):
    _require_manager(request.user)
    membership = get_object_or_404(
        Membership.objects.select_related("user", "role"), user_id=user_id
    )
    if membership.role.is_system and not permissions.is_admin(request.user):
        raise HttpError(403, "only an admin may change another admin")
    changes = payload.dict(exclude_unset=True, exclude={"reason"})
    if membership.user.pk == request.user.pk and ({"role", "status"} & set(changes)):
        raise HttpError(403, "you cannot change your own role or status")
    if "role" in changes:
        changes["role"] = roles.by_slug(changes["role"])
        if not permissions.can_assign_role(request.user, changes["role"]):
            raise HttpError(403, "only an admin may grant the admin role")
    before = _member_out(membership)
    with transaction.atomic():
        _guard_last_admin(membership, changes)
        for field, value in changes.items():
            setattr(membership, field, value)
        if "status" in changes:
            active = changes["status"] == MembershipStatus.ACTIVE
            membership.user.is_active = active
            membership.user.save(update_fields=["is_active"])
            membership.suspended_at = None if active else timezone.now()
            if active:
                membership.source = MembershipSource.EXPLICIT
        membership.save()
        if membership.status == MembershipStatus.ACTIVE and membership.role.grants("fly"):
            from apps.scrims.roster import ensure_pilot_for

            ensure_pilot_for(membership.user)
    after = _member_out(membership)
    record(
        actor=request.user,
        action="membership.updated",
        target=membership.user,
        reason=payload.reason,
        before={k: before[k] for k in changes},
        after={k: after[k] for k in changes},
    )
    return after


@router.delete("/team/members/{user_id}", response={204: None})
def remove_member(request: HttpRequest, user_id: int, payload: RemoveIn):
    _require_manager(request.user)
    membership = get_object_or_404(
        Membership.objects.select_related("user", "role"), user_id=user_id
    )
    if membership.role.is_system and not permissions.is_admin(request.user):
        raise HttpError(403, "only an admin may remove an admin")
    if membership.user.pk == request.user.pk:
        raise HttpError(403, "you cannot remove yourself")
    with transaction.atomic():
        _guard_last_admin(membership, {"status": MembershipStatus.REMOVED})
        membership.status = MembershipStatus.REMOVED
        membership.suspended_at = timezone.now()
        membership.save(update_fields=["status", "suspended_at"])
        membership.user.is_active = False
        membership.user.save(update_fields=["is_active"])
    record(
        actor=request.user,
        action="membership.removed",
        target=membership.user,
        reason=payload.reason,
    )
    return 204, None


@router.get("/team/invites", response=list[InviteOut])
def list_invites(request: HttpRequest):
    _require_manager(request.user)
    invites = (
        Invite.objects.filter(expires_at__gt=timezone.now(), uses_left__gt=0)
        .select_related("role")
        .order_by("-id")
    )
    return [_invite_out(request, i) for i in invites]


@router.post("/team/invites", response={201: InviteOut})
def create_invite(request: HttpRequest, payload: InviteIn):
    _require_manager(request.user)
    role = roles.by_slug(payload.role)
    if not permissions.can_assign_role(request.user, role):
        raise HttpError(403, "cannot create an invite for that role")
    invite = Invite.objects.create(
        role=role,
        uses_left=max(1, payload.uses),
        expires_at=timezone.now() + timedelta(hours=max(1, payload.expires_in_hours)),
        note=payload.note,
        created_by=request.user,
    )
    record(
        actor=request.user, action="invite.created", target=invite, after={"role": invite.role.slug}
    )
    return 201, _invite_out(request, invite)


@router.delete("/team/invites/{invite_id}", response={204: None})
def revoke_invite(request: HttpRequest, invite_id: int):
    _require_manager(request.user)
    invite = get_object_or_404(Invite, pk=invite_id)
    record(actor=request.user, action="invite.revoked", target=invite)
    invite.delete()
    return 204, None


@router.get("/team/admission-rules", response=list[AdmissionRuleOut])
def list_rules(request: HttpRequest):
    _require_manager(request.user)
    return [
        _rule_out(r)
        for r in AdmissionRule.objects.select_related("default_role").order_by(
            "kind", "entity_name"
        )
    ]


@router.post("/team/admission-rules", response={201: AdmissionRuleOut})
def create_rule(request: HttpRequest, payload: AdmissionRuleIn):
    _require_manager(request.user)
    role = roles.by_slug(payload.default_role)
    if not permissions.can_assign_role(request.user, role):
        raise HttpError(403, "cannot create a rule granting that role")
    if AdmissionRule.objects.filter(kind=payload.kind, entity_id=payload.entity_id).exists():
        raise HttpError(409, "a rule for that entity already exists")
    data = payload.dict()
    data["default_role"] = role
    rule = AdmissionRule.objects.create(**data, created_by=request.user)
    record(actor=request.user, action="admission_rule.created", target=rule, after=payload.dict())
    return 201, _rule_out(rule)


@router.patch("/team/admission-rules/{rule_id}", response=AdmissionRuleOut)
def patch_rule(request: HttpRequest, rule_id: int, payload: AdmissionRulePatch):
    _require_manager(request.user)
    rule = get_object_or_404(AdmissionRule, pk=rule_id)
    changes = payload.dict(exclude_unset=True)
    before = {k: getattr(rule, k) for k in changes}
    if "default_role" in changes:
        before["default_role"] = rule.default_role.slug
        changes["default_role"] = roles.by_slug(changes["default_role"])
        if not permissions.can_assign_role(request.user, changes["default_role"]):
            raise HttpError(403, "cannot grant that role")
    for field, value in changes.items():
        setattr(rule, field, value)
    rule.save()
    record(
        actor=request.user,
        action="admission_rule.updated",
        target=rule,
        before=before,
        after={k: (v.slug if isinstance(v, TeamRole) else v) for k, v in changes.items()},
    )
    return _rule_out(rule)


@router.delete("/team/admission-rules/{rule_id}", response={204: None})
def delete_rule(request: HttpRequest, rule_id: int):
    _require_manager(request.user)
    rule = get_object_or_404(AdmissionRule, pk=rule_id)
    record(actor=request.user, action="admission_rule.deleted", target=rule)
    rule.delete()
    return 204, None
