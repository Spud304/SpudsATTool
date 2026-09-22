from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts import roles, services
from apps.accounts.models import (
    AdmissionRule,
    AdmissionRuleKind,
    Invite,
    Membership,
    MembershipStatus,
    Role,
)
from apps.accounts.sso import SsoIdentity
from apps.audit.models import AuditLog

from .conftest import ADMIN_ID, admitted

pytestmark = pytest.mark.django_db


def test_env_admin_is_granted_on_login(team, admins, make_character):
    result = services.admit(make_character(ADMIN_ID, "Spud"))
    assert result.outcome == "env_admin" and result.admitted
    user, membership = admitted(result)
    assert membership.role.slug == Role.ADMIN and membership.is_leadership
    assert user.is_superuser
    assert AuditLog.objects.filter(action="membership.admin_granted").exists()
    # second login: existing
    assert services.admit(make_character(ADMIN_ID, "Spud")).outcome == "existing"


def test_first_login_is_not_admin(team, admins, make_character):
    result = services.admit(make_character(2, "Stranger"))
    assert result.outcome == "denied" and not result.admitted
    assert Membership.objects.count() == 0


def test_empty_admin_list_denies_everyone_with_hint(team, make_character):
    result = services.admit(make_character(ADMIN_ID, "Spud"))
    assert result.outcome == "no_admins" and not result.admitted


def test_invite_admits_once(team, admins, make_character):
    invite = Invite.objects.create(
        role=roles.by_slug(Role.THEORYCRAFTER),
        uses_left=1,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    result = services.admit(make_character(2, "Second"), invite_token=invite.token)
    assert result.outcome == "invite" and admitted(result)[1].role.slug == Role.THEORYCRAFTER
    invite.refresh_from_db()
    assert invite.uses_left == 0
    assert services.admit(make_character(3, "Third"), invite_token=invite.token).outcome == "denied"
    expired = Invite.objects.create(
        role=roles.by_slug(Role.PILOT), expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert (
        services.admit(make_character(4, "Fourth"), invite_token=expired.token).outcome == "denied"
    )


def test_alliance_rule(team, admins, make_character):
    AdmissionRule.objects.create(
        kind=AdmissionRuleKind.ALLIANCE, entity_id=99000001, default_role=roles.by_slug(Role.PILOT)
    )
    result = services.admit(make_character(2, "Second", alliance_id=99000001))
    assert result.outcome == "rule" and admitted(result)[1].source == "rule"
    assert services.admit(make_character(3, "Third", alliance_id=99000002)).outcome == "denied"


def test_removed_member_is_not_readmitted_by_rule(team, admins, make_character):
    AdmissionRule.objects.create(kind=AdmissionRuleKind.CORPORATION, entity_id=1000)
    _, membership = admitted(services.admit(make_character(2, "Second", corporation_id=1000)))
    membership.status = MembershipStatus.REMOVED
    membership.save()
    assert services.admit(make_character(2, "Second", corporation_id=1000)).outcome == "denied"


def test_owner_hash_change_detaches_character(team, admins, make_character):
    char = make_character(ADMIN_ID, "Spud", owner="owner-a")
    user, _ = admitted(services.admit(char))
    char = services.upsert_character(SsoIdentity(ADMIN_ID, "Spud", "owner-b", ()))
    assert char.user is None
    user.refresh_from_db()
    assert user.main_character is None
    assert AuditLog.objects.filter(action="character.owner_changed").exists()


def test_link_character(team, admins, make_character):
    user, _ = admitted(services.admit(make_character(ADMIN_ID, "Spud")))
    alt = make_character(2, "Alt")
    services.link_character(user, alt)
    assert user.characters.count() == 2
    invite = Invite.objects.create(
        role=roles.by_slug(Role.PILOT), expires_at=timezone.now() + timedelta(hours=1)
    )
    other, _ = admitted(services.admit(make_character(3, "Other"), invite_token=invite.token))
    with pytest.raises(ValueError):
        services.link_character(other, alt)


def test_grant_admin_command(team, make_character, capsys):
    make_character(5, "Recovered")
    call_command("grant_admin", "Recovered")
    assert Membership.objects.get(user__characters__character_id=5).role.slug == Role.ADMIN
    call_command("grant_admin", "777")  # not logged in yet
    assert "applies on first login" in capsys.readouterr().out
    assert Membership.objects.get(user__characters__character_id=777).role.slug == Role.ADMIN


def test_refresh_affiliations_grace_and_reactivation(team, admins, make_character, monkeypatch):
    AdmissionRule.objects.create(kind=AdmissionRuleKind.CORPORATION, entity_id=1000)
    _, membership = admitted(services.admit(make_character(2, "Pilot", corporation_id=1000)))

    class Left:
        def affiliations(self, ids):
            return [
                {"character_id": cid, "corporation_id": 2000, "alliance_id": None} for cid in ids
            ]

    monkeypatch.setattr(services, "get_client", lambda: Left())
    services.refresh_affiliations()
    membership.refresh_from_db()
    assert membership.status == MembershipStatus.ACTIVE and membership.rule_failed_since is not None

    membership.rule_failed_since = timezone.now() - timedelta(hours=25)
    membership.save()
    assert services.refresh_affiliations()["suspended"] == 1
    membership.refresh_from_db()
    assert membership.status == MembershipStatus.SUSPENDED and membership.user.is_active is False

    class Back:
        def affiliations(self, ids):
            return [
                {"character_id": cid, "corporation_id": 1000, "alliance_id": None} for cid in ids
            ]

    monkeypatch.setattr(services, "get_client", lambda: Back())
    assert services.refresh_affiliations()["reactivated"] == 1
    membership.refresh_from_db()
    assert membership.status == MembershipStatus.ACTIVE


def test_a_hand_suspension_is_not_lifted_by_a_matching_rule(
    client, team, admins, make_character, login_as
):
    AdmissionRule.objects.create(kind=AdmissionRuleKind.CORPORATION, entity_id=1000)
    user, _ = admitted(services.admit(make_character(2, "Pilot", corporation_id=1000)))
    login_as(role=None)  # env admin
    resp = client.patch(
        f"/api/team/members/{user.pk}",
        {"status": "suspended", "reason": "conduct"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    result = services.admit(make_character(2, "Pilot", corporation_id=1000))
    assert result.outcome == "suspended" and not result.admitted


def test_django_admin_access_is_for_env_admins_only(client, team, settings, make_character):
    settings.ADMIN_CHARACTER_IDS = [ADMIN_ID, 6]
    first, _ = admitted(services.admit(make_character(ADMIN_ID, "Spud")))
    other, _ = admitted(services.admit(make_character(6, "Second")))
    assert other.is_superuser and other.is_staff
    make_character(5, "Recovered")
    call_command("grant_admin", "Recovered")
    recovered = Membership.objects.get(user__characters__character_id=5)
    assert recovered.role.slug == Role.ADMIN and not recovered.user.is_superuser

    client.force_login(first)  # demotes the second env admin
    resp = client.patch(
        f"/api/team/members/{other.pk}", {"role": "pilot"}, content_type="application/json"
    )
    assert resp.status_code == 200, resp.content
    other.refresh_from_db()
    assert not other.is_superuser and not other.is_staff
