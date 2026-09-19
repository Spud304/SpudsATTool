import re

from playwright.sync_api import Browser, expect

from .conftest import SECOND_PILOT, open_as, uniq
from .data import ABSO_FIT, FACTION_FIT

FIT_URL = re.compile(r"/fits/\d+$")


def paste_fit(page, eft: str, name: str) -> str:
    page.goto("/fits")
    page.get_by_test_id("fits.new.eft").fill(eft)
    page.get_by_test_id("fits.new.name").fill(name)
    expect(page.get_by_test_id("fits.new.preview")).to_contain_text("Absolution")
    expect(page.get_by_test_id("fits.new.save")).to_be_enabled()
    page.get_by_test_id("fits.new.save").click()
    expect(page).to_have_url(FIT_URL)
    return page.url


def test_pilot_suggests_theorycrafter_activates_audit_records(login_as):
    pilot = login_as("pilot")
    pilot.page.goto("/fits")
    expect(pilot.page.get_by_test_id("fits.new.status")).to_have_count(
        0
    )  # pilots cannot pick a status
    url = paste_fit(pilot.page, ABSO_FIT, uniq("fit"))
    expect(pilot.page.get_by_test_id("fit.status.badge")).to_have_text("suggested")
    expect(pilot.page.get_by_test_id("fit.status")).to_have_count(0)  # no status panel for pilots
    expect(pilot.page.get_by_test_id("fit.save")).to_be_visible()  # own suggested fit is editable
    expect(pilot.page.get_by_test_id("fit.legality.verdict")).to_have_text("legal")

    theo = login_as("theorycrafter")
    theo.page.goto(url)
    theo.page.get_by_test_id("fit.status.select").select_option("active")
    theo.page.get_by_test_id("fit.status.reason").fill("pw looks good")
    theo.page.get_by_test_id("fit.status.apply").click()
    expect(theo.page.get_by_test_id("fit.status.badge")).to_have_text("active")
    expect(theo.page.get_by_test_id("toast").first).to_have_text("Fit saved")

    pilot.page.reload()
    expect(pilot.page.get_by_test_id("fit.status.badge")).to_have_text("active")
    expect(pilot.page.get_by_test_id("fit.save")).to_have_count(0)  # no longer the pilot's to edit

    admin = login_as("admin")
    admin.page.goto("/team/audit")
    admin.page.get_by_test_id("audit.filter").fill("fit.status_changed")
    expect(
        admin.page.get_by_test_id("audit.row").filter(has_text="pw looks good").first
    ).to_be_visible()


def test_pilot_cannot_edit_another_pilots_suggested_fit(login_as, browser: Browser):
    pilot = login_as("pilot")
    url = paste_fit(pilot.page, ABSO_FIT, uniq("fit"))

    other = open_as(browser, "pilot", SECOND_PILOT, "PW pilot 2")
    try:
        other.page.goto(url)
        expect(other.page.get_by_test_id("fit.status.badge")).to_have_text("suggested")
        expect(other.page.get_by_test_id("fit.save")).to_have_count(0)
        expect(other.page.get_by_test_id("fit.eft")).to_have_attribute("readonly", "")
    finally:
        other.context.close()


def test_faction_module_is_illegal_against_the_season_ruleset(login_as):
    theo = login_as("theorycrafter")
    paste_fit(theo.page, FACTION_FIT, uniq("faction"))
    expect(theo.page.get_by_test_id("fit.legality.verdict")).to_have_text("illegal")
    expect(theo.page.get_by_text("META_GROUP_NOT_ALLOWED")).to_be_visible()
