from datetime import timedelta

import pytest
from django.utils import timezone

from apps.scrims import sessions, sets, suggestions
from apps.scrims.models import Pilot
from tests.rules.engine import atxxii as at

pytestmark = pytest.mark.django_db


def _fly(theo, session_id, set_id, pilot, type_id, slot_no=1, round_no=1):
    sets.patch_assignment(
        theo, session_id, set_id, round_no, "US", slot_no, type_id=type_id, pilot_id=pilot.pk
    )


def test_history_counts_flights_and_skips_deleted_reset_and_archived(
    scrim, captain, theo, imported_atxxii
):
    one = Pilot.objects.get(name="Pilot One")
    cap = Pilot.objects.get(user=captain)
    earlier = sessions.create_session(
        captain, title="Last week", date=timezone.now() - timedelta(days=7)
    )
    set_a = sets.create_set(captain, earlier.pk)["id"]
    _fly(theo, earlier.pk, set_a, one, at.ASTARTE, slot_no=1)
    _fly(theo, earlier.pk, set_a, cap, at.ASTARTE, slot_no=2)
    sets.patch_round(theo, earlier.pk, set_a, 1, outcome="win")
    sets.add_round(theo, earlier.pk, set_a)  # copies both: Pilot One 2 flights, Cap 2 flights
    sets.patch_round(theo, earlier.pk, set_a, 2, outcome="reset")  # reset rounds do not count
    sets.add_round(theo, earlier.pk, set_a)
    sets.patch_round(theo, earlier.pk, set_a, 3, outcome="loss")

    rows = suggestions.pilot_history(at.ASTARTE)
    assert [(r["pilot_name"], r["flights"]) for r in rows] == [("Cap", 2), ("Pilot One", 2)]
    assert rows[0]["last_date"].startswith(earlier.date.date().isoformat())

    # The current scrim is excluded when asked, so tonight's own lineup does not count as history.
    tonight_set = sets.create_set(captain, scrim.pk)["id"]
    _fly(theo, scrim.pk, tonight_set, one, at.ASTARTE)
    from django.core.cache import cache

    cache.clear()
    by_name = lambda rows: {r["pilot_name"]: r["flights"] for r in rows}  # noqa: E731
    assert by_name(suggestions.pilot_history(at.ASTARTE)) == {"Cap": 2, "Pilot One": 3}
    assert by_name(suggestions.pilot_history(at.ASTARTE, exclude_session_id=scrim.pk)) == {
        "Cap": 2,
        "Pilot One": 2,
    }

    # Deleted rounds and archived scrims drop out.
    cache.clear()
    sets.delete_round(captain, earlier.pk, set_a, 3)
    assert [
        r["flights"] for r in suggestions.pilot_history(at.ASTARTE, exclude_session_id=scrim.pk)
    ] == [1, 1]
    cache.clear()
    sessions.archive_session(captain, earlier, "done")
    assert suggestions.pilot_history(at.ASTARTE, exclude_session_id=scrim.pk) == []


def test_history_endpoint(client, scrim, captain, theo, login_as):
    one = Pilot.objects.get(name="Pilot One")
    set_id = sets.create_set(captain, scrim.pk)["id"]
    _fly(theo, scrim.pk, set_id, one, at.KERES)
    login_as(character_id=6, name="Viewer", role="viewer")
    resp = client.get("/api/pilots/history", {"type_id": at.KERES})
    assert resp.status_code == 200 and resp.json()[0]["pilot_name"] == "Pilot One"
    assert (
        client.get("/api/pilots/history", {"type_id": at.KERES, "exclude_session": scrim.pk}).json()
        == []
    )
    client.post("/auth/logout")
    login_as(character_id=5, name="Guest", role="guest")
    assert client.get("/api/pilots/history", {"type_id": at.KERES}).status_code == 403
