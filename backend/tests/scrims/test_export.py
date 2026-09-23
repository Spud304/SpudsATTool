import csv
import io

import pytest

from apps.library.models import Archetype
from apps.scrims import export, sets
from apps.scrims.models import Pilot
from tests.rules.engine import atxxii as at

pytestmark = pytest.mark.django_db


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_match_log_rows_follow_the_sheet(scrim, captain, theo, of99_comp):
    doc = sets.create_set(captain, scrim.pk)
    set_id = doc["id"]
    sets.patch_set(theo, scrim.pk, set_id, comp_id=of99_comp.pk, our_side="B")
    who = Pilot.objects.get(name="Pilot One")
    sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 1, pilot_id=who.pk, is_flagship=True)
    sets.paste_opp_lineup(theo, scrim.pk, set_id, 1, "Bhaalgorn\nAstarte\nAstarte")
    sets.patch_assignment(theo, scrim.pk, set_id, 1, "OPP", 1, is_flagship=True)
    sets.put_ban(theo, scrim.pk, set_id, side="A", kind="standard", index=1, type_id=at.KERES)
    sets.put_ban(theo, scrim.pk, set_id, side="B", kind="standard", index=2, type_id=at.MAULUS)
    sets.patch_assignment(theo, scrim.pk, set_id, 1, "US", 3, died=True)
    sets.patch_round(theo, scrim.pk, set_id, 1, outcome="loss")
    sets.put_ban(
        theo,
        scrim.pk,
        set_id,
        side="B",
        kind="avalanche",
        index=1,
        type_id=at.ASHIMMU,
        in_effect_from_round=2,
    )
    sets.add_round(theo, scrim.pk, set_id)
    sets.patch_round(theo, scrim.pk, set_id, 2, outcome="reset")
    sets.add_round(theo, scrim.pk, set_id)
    sets.patch_round(theo, scrim.pk, set_id, 3, outcome="win")

    text = export.match_log_csv(scrim, {a.pk: a.name for a in Archetype.objects.all()})
    rows = rows_of(text)
    assert list(rows[0].keys()) == export.COLUMNS
    # 10 fielded slots x 2 fought rounds; the reset round is skipped
    assert len(rows) == 20 and {r["round"] for r in rows} == {"1", "3"}

    first = rows[0]
    assert first["pilot"] == "Pilot One" and first["ship"] == "Astarte" and first["flag"] == "1"
    assert first["fate"] == "1" and first["outcome"] == "0" and first["set"] == "1"
    assert (
        first["opp_ship1"] == "Bhaalgorn"
        and first["opp_ship3"] == "Astarte"
        and first["opp_ship4"] == ""
    )
    assert first["opp_flag_is"] == "Bhaalgorn" and first["our_ban_side"] == "Team B"
    assert first["team_a_ban1"] == "Keres" and first["team_b_ban2"] == "Maulus"
    assert (
        first["team_b_ban5"] == "Ashimmu"
    )  # avalanche bans fill the columns after the four standard ones
    assert (
        first["tournament"] == "ATXXII"
        and first["comp_name"] == "Armor Rush"
        and first["stage_code"] == "bracket"
    )
    assert first["ship_points"].isdigit() and first["hull_size"] == "FLAG"  # the flagship slot
    dead = next(r for r in rows if r["round"] == "1" and r["ship"] == "Absolution")
    assert dead["fate"] == "0" and dead["ship_points"] == "33"
    third = next(r for r in rows if r["round"] == "3")
    assert third["outcome"] == "1"


def test_csv_endpoint_and_filename(client, scrim, captain, login_as):
    sets.create_set(captain, scrim.pk)
    login_as(character_id=6, name="Viewer", role="viewer")
    resp = client.get(f"/api/scrims/{scrim.pk}/export.csv")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert (
        resp["Content-Disposition"]
        == f'attachment; filename="OF-99-{scrim.date.date().isoformat()}.csv"'
    )
    assert resp.content.decode().splitlines()[0] == ",".join(export.COLUMNS)
    client.post("/auth/logout")
    login_as(character_id=5, name="Guest", role="guest")
    assert client.get(f"/api/scrims/{scrim.pk}/export.csv").status_code == 403
