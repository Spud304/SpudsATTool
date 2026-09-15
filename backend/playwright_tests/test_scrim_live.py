"""Two people on one scrim page: writes from one browser land in the other over the event stream."""

import re

from playwright.sync_api import expect

from .conftest import uniq


def open_scrim(session, scrim_id: int):
    session.page.goto(f"/scrims/{scrim_id}")
    expect(session.page.get_by_test_id("scrim.stream.status")).to_have_text("live", timeout=15000)


def test_live_set_edits_reach_the_other_browser(login_as):
    captain = login_as("captain")
    theo = login_as("theorycrafter")
    pilot = login_as("pilot")
    tonight = captain.json("/api/scrims/vocab")  # warms the session; also checks the endpoint
    assert "bracket" in [s["code"] for s in tonight["stages"]]

    created = captain.api_call(
        "POST",
        "/api/scrims",
        {"title": uniq("live"), "date": "2036-01-01T19:00:00Z", "stage_code": "bracket"},
    )
    assert created.status == 201, created.text()
    scrim_id = created.json()["id"]

    # Captain starts set 1; the other two are already watching.
    open_scrim(pilot, scrim_id)
    open_scrim(theo, scrim_id)
    open_scrim(captain, scrim_id)
    captain.page.get_by_test_id("scrim.nosets.new").click()
    expect(captain.page.get_by_test_id("scrim.bans")).to_be_visible()
    expect(theo.page.get_by_test_id("scrim.bans")).to_be_visible()  # arrived over the stream
    expect(pilot.page.get_by_test_id("scrim.results")).to_be_visible()
    expect(theo.page.get_by_test_id(re.compile(r"^scrim\.bans\.chip\.\d+$"))).to_have_count(8)

    # Theorycrafter fills our slot 1 and the pilot's read-only row follows.
    theo.page.wait_for_selector("#scrim-hulls option", state="attached")
    ship = theo.page.get_by_test_id("scrim.ours.row.1.ship")
    ship.fill("Astarte")
    ship.press("Enter")
    expect(theo.page.get_by_test_id("scrim.ours.row.1.pts")).not_to_have_text("")
    expect(pilot.page.get_by_test_id("scrim.ours.row.1.ship")).to_have_text("Astarte")
    match = re.match(r"\d+", pilot.page.get_by_test_id("scrim.ours.row.1.pts").inner_text())
    assert match is not None
    points = int(match.group())
    assert points > 0

    # One ship fielded: the rest of our cap is conceded as handicap; a death adds its points on top.
    handicap = 200 - points
    expect(pilot.page.get_by_test_id("scrim.results.diff")).to_have_text(f"−{handicap}")
    theo.page.get_by_test_id("scrim.results.us.1").click()
    expect(pilot.page.get_by_test_id("scrim.results.diff")).to_have_text(f"−{handicap + points}")
    expect(pilot.page.get_by_test_id("scrim.results.us.1")).to_have_attribute("data-dead", "true")

    # Their second pick bans the Astarte: our row flags it everywhere.
    chip = theo.page.get_by_test_id("scrim.bans.chip.2.hull")
    chip.fill("Astarte")
    chip.press("Enter")
    expect(pilot.page.get_by_test_id("scrim.ours.row.1")).to_contain_text("banned")
    expect(pilot.page.get_by_test_id("scrim.bans.chip.2")).to_contain_text("Astarte")
    expect(captain.page.get_by_test_id("scrim.ours.legal")).not_to_have_text("legal")

    # Outcome + new round: avalanche chips appear, round 2 copies the lineup with deaths cleared.
    captain.page.get_by_test_id("scrim.results.outcome.loss").click()
    expect(theo.page.get_by_test_id(re.compile(r"^scrim\.bans\.avalanche\.\d+$"))).to_have_count(3)
    theo.page.get_by_test_id("scrim.results.addround").click()
    expect(pilot.page.get_by_test_id("scrim.results.round.2")).to_be_visible()
    pilot.page.get_by_test_id("scrim.results.round.2").click()
    expect(pilot.page.get_by_test_id("scrim.ours.row.1.ship")).to_have_text("Astarte")
    expect(pilot.page.get_by_test_id("scrim.results.us.1")).to_have_attribute("data-dead", "false")
    expect(
        theo.page.get_by_test_id(
            "scrim.sets.card." + str(theo.json(f"/api/scrims/{scrim_id}")["sets"][0]["id"])
        )
    ).to_contain_text("L")

    # Paste their lineup; presence shows who is on the page.
    theo.page.get_by_test_id("scrim.theirs.paste").click()
    theo.page.get_by_test_id("scrim.theirs.paste.text").fill("Vindicator\nNotAHull")
    theo.page.get_by_test_id("scrim.theirs.paste.apply").click()
    expect(theo.page.get_by_test_id("scrim.theirs.paste.unresolved")).to_contain_text("NotAHull")
    expect(pilot.page.get_by_test_id("scrim.theirs.row.1.ship")).to_have_text("Vindicator")
    me = pilot.json("/api/me")
    pilot_row = next(p for p in pilot.json("/api/pilots") if p["user_id"] == me["user_id"])
    captain.page.get_by_test_id(
        "scrim.attendance.more"
    ).click()  # the pilot never answered, so their row is folded
    expect(
        captain.page.get_by_test_id(f"scrim.attendance.row.{pilot_row['id']}.online")
    ).to_have_attribute("data-online", "true", timeout=20000)

    # Pilots cannot touch other people's slots; the API says so.
    assert (
        pilot.api_call(
            "PATCH",
            f"/api/scrims/{scrim_id}/sets/{theo.json(f'/api/scrims/{scrim_id}')['sets'][0]['id']}/rounds/1/US/1",
            {"type_id": None},
        ).status
        == 403
    )
