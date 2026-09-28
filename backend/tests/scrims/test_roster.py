import pytest

from apps.accounts import services as account_services
from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.scrims import roster, sessions
from apps.scrims.models import ChangeEvent, Pilot, SessionAttendance

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


def test_new_pilots_join_upcoming_scrims_only(scrim, captain, tonight):
    from datetime import timedelta

    last_week = sessions.create_session(captain, title="Old", date=tonight - timedelta(days=7))
    archived = sessions.create_session(captain, title="Gone", date=tonight + timedelta(days=1))
    sessions.archive_session(captain, archived, "cancelled")
    seq_before = scrim.event_seq

    late = make_member(300, "Late Joiner", Role.PILOT)  # admitted after the scrims were created
    pilot_row = Pilot.objects.get(user=late)
    rows = SessionAttendance.objects.filter(pilot=pilot_row)
    assert set(rows.values_list("session_id", flat=True)) == {scrim.pk}
    row = rows.get()
    assert row.rsvp == "none" and row.attendance == "none"
    assert not SessionAttendance.objects.filter(
        pilot=pilot_row, session__in=[last_week, archived]
    ).exists()
    # the open scrim pages hear about it
    scrim.refresh_from_db()
    assert scrim.event_seq == seq_before + 1
    assert ChangeEvent.objects.filter(session=scrim, kind="attendance").exists()

    # a second run adds nothing
    assert roster.attach_to_upcoming(pilot_row) == 0
    assert SessionAttendance.objects.filter(pilot=pilot_row).count() == 1

    # a hand-added merc and a reactivated pilot join too
    merc = roster.create_pilot(captain, name="Hired Late", is_merc=True)
    assert SessionAttendance.objects.filter(pilot=merc, session=scrim).exists()
    roster.update_pilot(captain, merc, status="inactive")
    SessionAttendance.objects.filter(pilot=merc).delete()
    roster.update_pilot(captain, merc, status="active")
    assert SessionAttendance.objects.filter(pilot=merc, session=scrim).exists()


def test_opponent_names_cannot_be_blank_and_a_pilot_keeps_its_own_user(captain, pilot):
    from apps.scrims.roster import ScrimError

    opponent = roster.create_opponent(captain, name="Hydra")
    with pytest.raises(ScrimError) as err:
        roster.update_opponent(captain, opponent, name="  ")
    assert err.value.status == 422
    mine = Pilot.objects.get(user=pilot)
    roster.update_pilot(captain, mine, user_id=pilot.pk, notes="same login")  # not a 409
