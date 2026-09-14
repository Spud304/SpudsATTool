import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import AdmissionRule, EveCharacter, Invite, Membership, Role, User
from apps.accounts.sso import SsoIdentity
from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.library import comps
from apps.library import services as fit_services
from apps.library.models import Archetype, Comp, Fit
from tests.conftest import ABSO_FIT

pytestmark = pytest.mark.django_db


def make_member(character_id: int, name: str, role: str) -> User:
    identity = SsoIdentity(
        character_id=character_id, name=name, owner_hash="o", scopes=("publicData",)
    )
    character = services.upsert_character(identity, None)
    user = services.ensure_user(character)
    services._set_membership(user, role=role, source="explicit", note="test")
    return user


def test_cleanup_removes_only_playwright_rows(library_sde, imported_atxxii, settings):
    settings.DEV_LOGIN_ENABLED = True
    pw_user = make_member(900_000_003, "PW theorycrafter", Role.THEORYCRAFTER)
    real_user = make_member(42, "Real", Role.THEORYCRAFTER)

    fit_services.create_fit(pw_user, eft_text=ABSO_FIT, name="pw_fit_1", status="active")
    fit_services.create_fit(real_user, eft_text=ABSO_FIT, name="Real fit", status="active")
    comps.create_comp(pw_user, name="pw_comp_1")
    comps.create_comp(real_user, name="Real comp")
    comps.create_archetype(pw_user, name="pw_arch")
    Invite.objects.create(note="pw_invite", expires_at=timezone.now())
    Invite.objects.create(note="real invite", expires_at=timezone.now())
    AdmissionRule.objects.create(kind="corporation", entity_id=900_000_005, entity_name="pw")
    AdmissionRule.objects.create(kind="corporation", entity_id=98_000_001, entity_name="real")
    record(actor=real_user, action="x.y", target_label="pw_fit_1")
    record(actor=real_user, action="x.y", target_label="kept")

    call_command("playwright_cleanup")

    assert list(Fit.objects.values_list("name", flat=True)) == ["Real fit"]
    assert list(Comp.objects.values_list("name", flat=True)) == ["Real comp"]
    assert not Archetype.objects.filter(name__startswith="pw_").exists()
    assert list(Invite.objects.values_list("note", flat=True)) == ["real invite"]
    assert list(AdmissionRule.objects.values_list("entity_id", flat=True)) == [98_000_001]
    assert not User.objects.filter(pk=pw_user.pk).exists()
    assert not EveCharacter.objects.filter(character_id=900_000_003).exists()
    assert Membership.objects.filter(user=real_user).exists()
    assert not AuditLog.objects.filter(actor=pw_user).exists()
    assert not AuditLog.objects.filter(target_label="pw_fit_1").exists()
    assert AuditLog.objects.filter(target_label="kept").exists()


def test_cleanup_refuses_outside_dev(settings):
    settings.DEV_LOGIN_ENABLED = False
    with pytest.raises(CommandError):
        call_command("playwright_cleanup")
