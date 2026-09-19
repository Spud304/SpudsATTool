import re

from playwright.sync_api import expect

from .conftest import uniq
from .data import ABSO_FIT, OF99_HULLS

COMP_URL = re.compile(r"/comps/\d+$")


def test_theorycrafter_builds_saves_and_clones_a_legal_comp(login_as):
    theo = login_as("theorycrafter")
    created = theo.api_call(
        "POST",
        "/api/fits",
        {"eft_text": ABSO_FIT, "name": uniq("fit"), "pyfa_summary": "", "status": "active"},
    )
    assert created.status == 201, created.text()
    fit_id = str(created.json()["id"])

    name = uniq("comp")
    theo.page.goto("/comps")
    theo.page.get_by_test_id("comps.new.name").fill(name)
    theo.page.get_by_test_id("comps.new.status").select_option("construction")
    theo.page.get_by_test_id("comps.new.create").click()
    expect(theo.page).to_have_url(COMP_URL)
    expect(theo.page.get_by_test_id("toast").first).to_have_text("Comp created")
    url = theo.page.url
    expect(theo.page.get_by_test_id("comp.status.badge")).to_have_text("construction")

    # the hull picker reverts unknown names, so wait until the ship list is loaded
    expect(theo.page.locator("#builder-hulls option").first).to_be_attached()
    for i, hull in enumerate(OF99_HULLS, start=1):
        field = theo.page.get_by_test_id(f"comp.slot.{i}.hull")
        field.fill(hull)
        field.press("Enter")
        expect(field).to_have_value(hull)
    expect(theo.page.get_by_test_id("comp.budget.total")).to_have_text("200 / 200")
    expect(theo.page.get_by_test_id("comp.budget.status")).to_have_text("EXACT")
    expect(theo.page.get_by_test_id("comp.budget.legal")).to_have_text("legal")

    theo.page.get_by_test_id("comp.slot.3.fit").select_option(fit_id)
    expect(theo.page.get_by_test_id("comp.slot.3.link")).to_have_text("L1")
    theo.page.get_by_test_id("comp.slot.1.warp").fill("40")
    theo.page.get_by_test_id("comp.notes").fill("pw notes")

    theo.page.get_by_test_id("comp.save").click()
    expect(theo.page.get_by_test_id("comp.save")).to_be_disabled()  # remounted clean after save

    theo.page.reload()
    expect(theo.page.get_by_test_id("comp.slot.1.hull")).to_have_value("Astarte")
    expect(theo.page.get_by_test_id("comp.slot.10.hull")).to_have_value("Maulus")
    expect(theo.page.get_by_test_id("comp.slot.3.fit")).to_have_value(fit_id)
    expect(theo.page.get_by_test_id("comp.slot.1.warp")).to_have_value("40")
    expect(theo.page.get_by_test_id("comp.notes")).to_have_value("pw notes")
    expect(theo.page.get_by_test_id("comp.budget.total")).to_have_text("200 / 200")

    theo.page.get_by_test_id("comp.clone").click()
    expect(theo.page).not_to_have_url(url)
    expect(theo.page.get_by_test_id("comp.name")).to_have_value(f"{name} (copy)")
    expect(theo.page.get_by_test_id("comp.slot.3.fit")).to_have_value(fit_id)

    pilot = login_as("pilot")
    pilot.page.goto(url)
    expect(pilot.page.get_by_test_id("comp.name")).to_have_text(name)
    expect(pilot.page.get_by_test_id("comp.save")).to_have_count(0)
    expect(pilot.page.get_by_test_id("comp.status")).to_have_count(0)
    expect(pilot.page.get_by_test_id("comp.budget.total")).to_have_text("200 / 200")

    theo.page.goto("/comps")
    theo.page.get_by_test_id("comps.search").fill(name)
    expect(theo.page.get_by_test_id(re.compile(r"comps\.row\."))).to_have_count(
        2
    )  # original and copy


def test_pilots_comp_lands_in_suggested_and_the_review_queue(login_as):
    pilot = login_as("pilot")
    name = uniq("idea")
    pilot.page.goto("/comps")
    expect(pilot.page.get_by_test_id("comps.new.status")).to_have_count(0)
    pilot.page.get_by_test_id("comps.new.name").fill(name)
    pilot.page.get_by_test_id("comps.new.create").click()
    expect(pilot.page).to_have_url(COMP_URL)
    expect(pilot.page.get_by_test_id("comp.status.badge")).to_have_text("suggested")
    expect(pilot.page.get_by_test_id("comp.save")).to_be_visible()

    theo = login_as("theorycrafter")
    theo.page.goto("/")
    expect(theo.page.get_by_test_id("dash.review")).to_contain_text(name)
