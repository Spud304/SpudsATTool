from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.rules.models import PointTableVersion
from apps.scrims import roster, sessions
from apps.scrims.models import Pilot, SessionAttendance

pytestmark = pytest.mark.django_db


def test_create_pins_point_table_and_precreates_attendance(
    imported_atxxii, captain, pilot, tonight
):
    ruleset, _ = imported_atxxii
    inactive = roster.create_pilot(captain, name="Old Hand")
    roster.update_pilot(captain, inactive, status="inactive")
    opp = roster.create_opponent(captain, name="Only Fleets")
    session = sessions.create_session(
        captain, title=" OF 99 ", date=tonight, opponent_id=opp.pk, stage_code="bracket"
    )
    assert session.title == "OF 99" and session.ruleset == ruleset
    assert session.point_table_version == PointTableVersion.objects.get(
        ruleset=ruleset, is_current=True
    )
    assert session.stage is not None and session.stage.code == "bracket"
    names = set(session.attendance.values_list("pilot__name", flat=True))
    assert names == {"Cap", "Pilot One"}  # inactive pilots are not invited
    assert AuditLog.objects.filter(action="scrim.created").exists()


def test_create_validation(imported_atxxii, captain, tonight):
    with pytest.raises(sessions.ScrimError) as exc:
        sessions.create_session(captain, title="x", date=tonight, stage_code="nope")
    assert exc.value.status == 422
    with pytest.raises(sessions.ScrimError):
        sessions.create_session(captain, title="x", date=tonight, kind="ladder")
    with pytest.raises(sessions.ScrimError):
        sessions.create_session(captain, title="  ", date=tonight)


def test_create_needs_a_cost_table(imported_atxxii, captain, tonight):
    PointTableVersion.objects.update(is_current=False)
    with pytest.raises(sessions.ScrimError) as exc:
        sessions.create_session(captain, title="x", date=tonight)
    assert "cost table" in str(exc.value)


def test_rsvp_rules(imported_atxxii, captain, pilot, viewer, tonight):
    session = sessions.create_session(captain, title="OF 99", date=tonight)
    with pytest.raises(sessions.ScrimError) as exc:
        sessions.set_rsvp(pilot, session, "maybe")
    assert exc.value.status == 422
    row = sessions.set_rsvp(pilot, session, "maybe", "late from work")
    assert row.rsvp == "maybe" and row.rsvp_reason == "late from work" and row.rsvp_at
    row = sessions.set_rsvp(pilot, session, "yes", "stale reason")
    assert row.rsvp == "yes" and row.rsvp_reason == ""
    with pytest.raises(sessions.ScrimError) as no_pilot:
        sessions.set_rsvp(viewer, session, "yes")
    assert no_pilot.value.status == 403
    assert sessions.tally(session) == {"yes": 1, "no": 0, "maybe": 0, "none": 1}

    old = sessions.create_session(
        captain, title="Last week", date=timezone.now() - timedelta(days=3)
    )
    with pytest.raises(sessions.ScrimError) as past:
        sessions.set_rsvp(pilot, old, "yes")
    assert past.value.status == 409


def test_new_pilot_is_already_on_open_sessions(imported_atxxii, captain, tonight):
    session = sessions.create_session(captain, title="OF 99", date=tonight)
    late_joiner = roster.create_pilot(captain, name="Late Joiner")
    assert SessionAttendance.objects.filter(session=session, pilot=late_joiner).exists()
    row = sessions.set_attendance(captain, session, late_joiner, "present")
    assert row.attendance == "present"


def test_attendance_and_no_show(imported_atxxii, captain, pilot, tonight):
    session = sessions.create_session(captain, title="OF 99", date=tonight)
    who = Pilot.objects.get(user=pilot)
    with pytest.raises(sessions.ScrimError) as exc:
        sessions.set_attendance(captain, session, who, "no_show")
    assert exc.value.status == 422
    row = sessions.set_attendance(captain, session, who, "no_show", "said yes, never showed")
    assert row.removed_by == captain and row.removed_at and row.removed_reason
    entry = AuditLog.objects.get(action="scrim.no_show_removed")
    assert entry.reason == "said yes, never showed" and entry.after == {"pilot": "Pilot One"}
    row = sessions.set_attendance(captain, session, who, "late")
    assert row.removed_by is None and row.removed_reason == ""
    assert AuditLog.objects.filter(action="scrim.attendance_set").count() == 1
    with pytest.raises(sessions.ScrimError):
        sessions.set_attendance(captain, session, who, "vanished")


def test_update_and_archive(imported_atxxii, captain, tonight):
    session = sessions.create_session(captain, title="OF 99", date=tonight)
    sessions.update_session(
        captain, session, title="OF 99 v2", system_name=" Jita ", default_our_side="B"
    )
    session.refresh_from_db()
    assert (
        session.title == "OF 99 v2"
        and session.system_name == "Jita"
        and session.default_our_side == "B"
    )
    entry = AuditLog.objects.get(action="scrim.updated")
    assert entry.before["title"] == "OF 99" and entry.after["side"] == "B"
    sessions.archive_session(captain, session, "duplicate")
    assert session.is_archived and AuditLog.objects.filter(action="scrim.archived").exists()
