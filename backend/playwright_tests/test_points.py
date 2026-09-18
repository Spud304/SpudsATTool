"""The points viewer: every hull with class, size and points; sort and filter; and the scratchpad's compact copy."""

import re

from playwright.sync_api import expect


def test_points_page_sorts_filters_and_remembers(login_as):
    pilot = login_as("pilot")
    page = pilot.page
    page.goto("/points")
    count = page.get_by_test_id("points.count")
    expect(count).to_have_text(re.compile(r"^(\d+) of \1 hulls$"))
    total = int(count.inner_text().split()[0])
    assert total > 50

    # Default order is points descending: the first row costs at least as much as the second.
    rows = page.locator("[data-testid^=points\\.row\\.]")
    first = int(rows.nth(0).locator("td").nth(3).inner_text())
    second = int(rows.nth(1).locator("td").nth(3).inner_text())
    assert first >= second
    expect(page.get_by_test_id("points.sort.points")).to_have_attribute("data-dir", "desc")

    # Sorting by name puts Astarte near the top; clicking again reverses.
    page.get_by_test_id("points.sort.name").click()
    expect(page.get_by_test_id("points.sort.name")).to_have_attribute("data-dir", "asc")
    names_asc = [t.strip() for t in rows.locator("td:first-child").all_inner_texts()]
    assert names_asc == sorted(names_asc, key=str.casefold)
    page.get_by_test_id("points.sort.name").click()
    expect(page.get_by_test_id("points.sort.name")).to_have_attribute("data-dir", "desc")

    # Text filter narrows the list and the count says so; Clear resets it.
    page.get_by_test_id("points.filter.text").fill("astarte")
    expect(count).to_have_text(re.compile(rf"^1 of {total} hulls$"))
    expect(rows.first.locator("td").first).to_have_text("Astarte")
    page.get_by_test_id("points.filter.text").fill("astarte zzz")
    expect(count).to_have_text(re.compile(rf"^0 of {total} hulls$"))
    page.get_by_test_id("points.clear").click()
    expect(count).to_have_text(re.compile(rf"^{total} of {total} hulls$"))

    # The sort and a filter survive a reload.
    page.get_by_test_id("points.filter.size").select_option("BS")
    page.reload()
    expect(page.get_by_test_id("points.sort.name")).to_have_attribute("data-dir", "desc")
    expect(page.get_by_test_id("points.filter.size")).to_have_value("BS")
    page.get_by_test_id("points.clear").click()


def test_scratchpad_points_panel_fills_the_next_empty_slot(login_as):
    theo = login_as("theorycrafter")
    page = theo.page
    page.goto("/scratchpad")
    panel = page.get_by_test_id("scratchpad.points")
    panel.get_by_test_id("points.filter.text").fill("astarte")
    panel.locator("[data-testid^=points\.row\.]").first.click()
    expect(page.get_by_test_id("scratchpad.slot.1.hull")).to_have_value("Astarte")
    panel.locator("[data-testid^=points\.row\.]").first.click()
    expect(page.get_by_test_id("scratchpad.slot.2.hull")).to_have_value("Astarte")
