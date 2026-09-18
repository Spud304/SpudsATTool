"""After the night: review tab, CSV, history with restore, share links and the pilot card."""

import re

from playwright.sync_api import Browser, expect

from .conftest import BASE_URL, uniq


def test_review_history_share_and_card(login_as, browser: Browser):
    captain = login_as("captain")
    pilot = login_as("pilot")
    created = captain.api_call(
        "POST",
        "/api/scrims",
        {"title": uniq("review"), "date": "2036-01-01T19:00:00Z", "stage_code": "bracket"},
    )
    scrim_id = created.json()["id"]
    base = f"/api/scrims/{scrim_id}"
    me = pilot.json("/api/me")
    pilot_row = next(p for p in pilot.json("/api/pilots") if p["user_id"] == me["user_id"])

    # A set with a fielded slot for the pilot, a death and an outcome, all through the API.
    set_id = captain.api_call("POST", f"{base}/sets", {}).json()["id"]
    ships = captain.json("/api/rulesets/ATXXII/ships")
    astarte = next(s["type_id"] for s in ships if s["name"] == "Astarte")
    captain.api_call(
        "PATCH",
        f"{base}/sets/{set_id}/rounds/1/US/1",
        {"type_id": astarte, "pilot_id": pilot_row["id"]},
    )
    captain.api_call("PATCH", f"{base}/sets/{set_id}/rounds/1/US/1", {"died": True})
    captain.api_call("PATCH", f"{base}/sets/{set_id}/rounds/1", {"outcome": "loss"})

    # Review tab: the record and the death show up.
    captain.page.goto(f"/scrims/{scrim_id}")
    captain.page.get_by_test_id("scrim.header.view.review").click()
    expect(captain.page.get_by_test_id("scrim.review.record")).to_contain_text("0–1")
    expect(captain.page.get_by_test_id(f"scrim.review.set.{set_id}.round.1")).to_contain_text(
        "Astarte"
    )
    expect(captain.page.get_by_test_id("scrim.review.pilots")).to_contain_text("PW pilot")

    # CSV: header and one row for the fielded slot.
    csv = captain.api_call("GET", f"{base}/export.csv")
    assert csv.status == 200 and csv.headers["content-type"].startswith("text/csv")
    lines = csv.text().splitlines()
    assert lines[0].startswith("date,pilot,ship,fate,set,round,outcome") and len(lines) == 2
    assert lines[1].split(",")[1:4] == ["PW pilot", "Astarte", "0"]

    # Delete the set from the board, then restore it from History.
    captain.page.get_by_test_id("scrim.header.view.board").click()
    captain.page.once("dialog", lambda d: d.accept("pw wrong set"))
    captain.page.get_by_test_id("scrim.bans.menu").click()
    captain.page.get_by_test_id("scrim.menu.delete-set").click()
    expect(captain.page.get_by_test_id("scrim.nosets")).to_be_visible()
    captain.page.get_by_test_id("scrim.header.history").click()
    expect(captain.page.get_by_test_id(f"scrim.history.deleted.set.{set_id}")).to_be_visible()
    expect(captain.page.get_by_test_id("scrim.history")).to_contain_text("pw wrong set")
    captain.page.get_by_test_id(f"scrim.history.deleted.set.{set_id}.restore").click()
    expect(captain.page.get_by_test_id(f"scrim.history.deleted.set.{set_id}")).to_have_count(0)
    captain.page.get_by_test_id("scrim.history.close").click()
    expect(captain.page.get_by_test_id("scrim.ours.row.1.ship")).to_have_value("Astarte")

    # Share link: a fresh browser context with no login sees the board, live, without fit text.
    captain.page.get_by_test_id("scrim.header.share").click()
    captain.page.get_by_test_id("scrim.share.create").click()
    url_el = captain.page.get_by_test_id(re.compile(r"^scrim\.share\.link\.\d+\.url$")).first
    expect(url_el).to_be_visible()
    share_url = url_el.inner_text().strip()
    assert share_url.startswith(BASE_URL + "/share/")
    captain.page.get_by_test_id("scrim.share.close").click()

    outsider = browser.new_context(base_url=BASE_URL)
    try:
        page = outsider.new_page()
        page.goto(share_url)
        expect(page.get_by_test_id("scrim.stream.status")).to_have_text("live", timeout=15000)
        expect(page.get_by_test_id("scrim.header")).to_contain_text("shared view")
        expect(page.get_by_test_id("scrim.header.export")).to_have_count(0)
        expect(page.get_by_test_id("scrim.fits")).to_have_count(0)
        expect(page.get_by_test_id("scrim.ours.row.1.ship")).to_have_text("Astarte")
        # A live change from the captain arrives on the shared page.
        captain.page.get_by_test_id("scrim.results.us.1").click()  # toggles the death off
        expect(page.get_by_test_id("scrim.results.us.1")).to_have_attribute("data-dead", "false")
        assert outsider.request.get(f"{base}").status == 401  # the token opens nothing else
    finally:
        outsider.close()

    # Pilot card: the pilot sees their own slot big.
    pilot.page.goto(f"/scrims/{scrim_id}/me")
    expect(pilot.page.get_by_test_id("pilotcard.ship")).to_have_text("Astarte")
    expect(pilot.page.get_by_test_id("pilotcard.fit")).to_contain_text("none chosen")

    # Revoked link stops working.
    links = captain.json(f"{base}/share")
    captain.api_call("DELETE", f"{base}/share/{links[0]['id']}")
    assert captain.api.get(f"/api/share/{links[0]['token']}").status == 404
