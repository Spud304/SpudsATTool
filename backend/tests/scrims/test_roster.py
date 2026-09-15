import pytest

from apps.accounts import services as account_services
from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.scrims import roster
from apps.scrims.models import Pilot

from .conftest import make_member

pytestmark = pytest.mark.django_db


def test_members_who_can_fly_get_a_pilot(captain, pilot, viewer):
    assert Pilot.objects.filter(user=captain, name="Cap").exists()
    assert Pilot.objects.filter(user=pilot, name="Pilot One").exists()
    assert not Pilot.objects.filter(user=viewer).exists()


def test_relogin_does_not_duplicate(pilot):
    account_services._set_membership(pilot, role=Role.PILOT, source="explicit")
    account_services._set_membership(pilot, role=Role.THEORYCRAFTER, source="explicit")
    assert Pilot.objects.filter(user=pilot).count() == 1


def test_unlinked_pilot_is_adopted_on_login(captain):
    merc = roster.create_pilot(captain, name="Fryon", is_merc=True)
    user = make_member(200, "Fryon", Role.PILOT)
    merc.refresh_from_db()
    assert merc.user == user and Pilot.objects.filter(name__iexact="fryon").count() == 1


def test_name_collision_with_a_linked_pilot_gets_a_suffix(pilot):
    other = make_member(201, "Pilot One", Role.PILOT)
    assert Pilot.objects.get(user=other).name == f"Pilot One ({other.pk})"


def test_manual_pilot_and_link(captain, viewer):
    merc = roster.create_pilot(captain, name=" Hired Gun ", is_merc=True, roles_text="Logi")
    assert merc.name == "Hired Gun" and merc.is_merc
    assert AuditLog.objects.filter(action="pilot.created").exists()
    with pytest.raises(roster.ScrimError) as exc:
        roster.create_pilot(captain, name="hired gun")
    assert exc.value.status == 409

    roster.update_pilot(captain, merc, user_id=viewer.pk, status="inactive")
    merc.refresh_from_db()
    assert merc.user == viewer and merc.status == "inactive"
    with pytest.raises(roster.ScrimError) as taken:
        roster.create_pilot(captain, name="Another", user_id=viewer.pk)
    assert taken.value.status == 409
    with pytest.raises(roster.ScrimError):
        roster.update_pilot(captain, merc, status="retired")


def test_opponents(captain):
    opp = roster.create_opponent(captain, name="Only Fleets", notes="kite heavy")
    with pytest.raises(roster.ScrimError):
        roster.create_opponent(captain, name="Only Fleets")
    roster.update_opponent(captain, opp, is_active=False)
    assert not opp.is_active
    assert AuditLog.objects.filter(action="opponent.updated").exists()
