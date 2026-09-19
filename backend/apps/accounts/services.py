"""Character upsert, admission, alt linking, and the periodic affiliation re-check."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.core.models import Team
from apps.esi.client import EsiError, get_client

from .models import (
    AdmissionRule,
    EveCharacter,
    Invite,
    Membership,
    MembershipSource,
    MembershipStatus,
    Role,
    User,
)
from .sso import SsoIdentity

log = logging.getLogger(__name__)


@dataclass
class AdmitResult:
    user: User | None
    membership: Membership | None
    outcome: str  # env_admin | existing | invite | rule | suspended | denied | no_admins

    @property
    def admitted(self) -> bool:
        return self.membership is not None and self.membership.status == MembershipStatus.ACTIVE


def fetch_affiliation(character_id: int) -> dict | None:
    try:
        data = get_client().character_public(character_id)
    except EsiError as exc:
        log.warning("could not fetch affiliation for %s: %s", character_id, exc)
        return None
    return {"corporation_id": data.get("corporation_id"), "alliance_id": data.get("alliance_id")}


def upsert_character(identity: SsoIdentity, affiliation: dict | None = None) -> EveCharacter:
    now = timezone.now()
    with transaction.atomic():
        char, created = EveCharacter.objects.select_for_update().get_or_create(
            character_id=identity.character_id,
            defaults={"name": identity.name, "owner_hash": identity.owner_hash},
        )
        if not created:
            transferred = (
                identity.owner_hash and char.owner_hash and char.owner_hash != identity.owner_hash
            )
            if transferred:
                previous = char.user
                record(
                    actor=None,
                    action="character.owner_changed",
                    target=char,
                    before={
                        "owner_hash": char.owner_hash,
                        "user_id": previous.pk if previous else None,
                    },
                    after={"owner_hash": identity.owner_hash},
                )
                char.user = None
                if previous is not None and previous.main_character_id == char.character_id:
                    previous.main_character = None
                    previous.save(update_fields=["main_character"])
            if identity.owner_hash:
                char.owner_hash = identity.owner_hash
            if identity.name:
                char.name = identity.name
        if affiliation:
            char.corporation_id = affiliation.get("corporation_id")
            char.alliance_id = affiliation.get("alliance_id")
            char.affiliation_checked_at = now
        char.last_login_at = now
        char.save()
    return char


def ensure_user(character: EveCharacter) -> User:
    if character.user is not None:
        return character.user
    user = User.objects.create_user(
        username=f"char:{character.character_id}", display_name=character.name
    )
    character.user = user
    character.save(update_fields=["user"])
    user.main_character = character
    user.save(update_fields=["main_character"])
    return user


def matching_rule(characters) -> AdmissionRule | None:
    rules = list(AdmissionRule.objects.filter(enabled=True))
    for character in characters:
        for rule in rules:
            if rule.matches(character):
                return rule
    return None


def _set_membership(user: User, *, role, source: str, note: str = "") -> Membership:
    from . import roles

    team_role = roles.by_slug(role)
    membership, _ = Membership.objects.update_or_create(
        user=user,
        defaults={
            "role": team_role,
            "status": MembershipStatus.ACTIVE,
            "source": source,
            "suspended_at": None,
            "rule_failed_since": None,
            "note": note,
        },
    )
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    if team_role.grants("fly"):
        from apps.scrims.roster import ensure_pilot_for  # roster row for anyone who can fly

        ensure_pilot_for(user)
    return membership


def grant_admin(character: EveCharacter, *, source: str, actor=None) -> Membership:
    user = ensure_user(character)
    membership = _set_membership(user, role=Role.ADMIN, source=source)
    if not membership.is_leadership:
        membership.is_leadership = True
        membership.save(update_fields=["is_leadership"])
    if not (user.is_staff and user.is_superuser):
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])
    record(actor=actor, action="membership.admin_granted", target=user, after={"source": source})
    return membership


def admit(character: EveCharacter, *, invite_token: str | None = None) -> AdmitResult:
    """Decide whether a freshly authenticated character may use the site."""
    with transaction.atomic():
        if character.character_id in settings.ADMIN_CHARACTER_IDS:
            user = ensure_user(character)
            existing = getattr(user, "membership", None)
            if (
                existing is None
                or not existing.role.is_system
                or existing.status != MembershipStatus.ACTIVE
            ):
                membership = grant_admin(character, source=MembershipSource.ENV_ADMIN)
                return AdmitResult(user, membership, "env_admin")
            return AdmitResult(user, existing, "existing")

        user = character.user
        existing = getattr(user, "membership", None) if user else None
        if existing is not None:
            if existing.status == MembershipStatus.ACTIVE:
                return AdmitResult(user, existing, "existing")
            if existing.status == MembershipStatus.SUSPENDED and matching_rule(
                user.characters.all()
            ):
                membership = _set_membership(user, role=existing.role, source=MembershipSource.RULE)
                record(actor=user, action="membership.reactivated_by_rule", target=user)
                return AdmitResult(user, membership, "rule")

        if invite_token:
            invite = Invite.objects.select_for_update().filter(token=invite_token).first()
            if invite is not None and invite.is_valid:
                user = ensure_user(character)
                membership = _set_membership(
                    user, role=invite.role, source=MembershipSource.INVITE, note=invite.note
                )
                invite.uses_left -= 1
                invite.save(update_fields=["uses_left"])
                record(
                    actor=user,
                    action="membership.admitted_by_invite",
                    target=user,
                    after={"role": invite.role.slug, "invite_id": invite.pk},
                )
                return AdmitResult(user, membership, "invite")

        removed = existing is not None and existing.status == MembershipStatus.REMOVED
        if not removed:
            rule = matching_rule([character])
            if rule is not None:
                user = ensure_user(character)
                membership = _set_membership(
                    user, role=rule.default_role, source=MembershipSource.RULE
                )
                record(
                    actor=user,
                    action="membership.admitted_by_rule",
                    target=user,
                    after={"role": rule.default_role.slug, "rule_id": rule.pk},
                )
                return AdmitResult(user, membership, "rule")

        if not settings.ADMIN_CHARACTER_IDS:
            return AdmitResult(user, existing, "no_admins")
        outcome = (
            "suspended" if existing and existing.status == MembershipStatus.SUSPENDED else "denied"
        )
        return AdmitResult(user, existing, outcome)


def link_character(user: User, character: EveCharacter) -> EveCharacter:
    if character.user is not None and character.user_id != user.pk:
        raise ValueError("character already belongs to another member")
    character.user = user
    character.save(update_fields=["user"])
    record(actor=user, action="character.linked", target=character)
    return character


def suspend_membership(membership: Membership, *, actor=None, reason: str = "") -> None:
    membership.status = MembershipStatus.SUSPENDED
    membership.suspended_at = timezone.now()
    membership.save(update_fields=["status", "suspended_at"])
    membership.user.is_active = False
    membership.user.save(update_fields=["is_active"])
    record(actor=actor, action="membership.suspended", target=membership.user, reason=reason)


def refresh_affiliations() -> dict:
    """Hourly: update corp/alliance for every known character and re-apply admission rules."""
    characters = list(EveCharacter.objects.all())
    updated = 0
    if characters:
        rows = get_client().affiliations([c.character_id for c in characters])
        by_id = {row["character_id"]: row for row in rows}
        now = timezone.now()
        for character in characters:
            row = by_id.get(character.character_id)
            if row is None:
                continue
            character.corporation_id = row.get("corporation_id")
            character.alliance_id = row.get("alliance_id")
            character.affiliation_checked_at = now
            updated += 1
        EveCharacter.objects.bulk_update(
            characters, ["corporation_id", "alliance_id", "affiliation_checked_at"]
        )

    grace = timedelta(hours=Team.get_solo().affiliation_grace_hours)
    now = timezone.now()
    suspended = reactivated = 0
    for membership in Membership.objects.filter(source=MembershipSource.RULE).select_related(
        "user"
    ):
        still_matches = matching_rule(membership.user.characters.all()) is not None
        if membership.status == MembershipStatus.ACTIVE and not still_matches:
            if membership.rule_failed_since is None:
                membership.rule_failed_since = now
                membership.save(update_fields=["rule_failed_since"])
            elif now - membership.rule_failed_since >= grace:
                suspend_membership(
                    membership, reason="no longer matches any admission rule after the grace period"
                )
                suspended += 1
        elif still_matches and membership.rule_failed_since is not None:
            membership.rule_failed_since = None
            if membership.status == MembershipStatus.SUSPENDED:
                _set_membership(membership.user, role=membership.role, source=MembershipSource.RULE)
                record(actor=None, action="membership.reactivated_by_rule", target=membership.user)
                reactivated += 1
            else:
                membership.save(update_fields=["rule_failed_since"])
    return {"characters_updated": updated, "suspended": suspended, "reactivated": reactivated}
