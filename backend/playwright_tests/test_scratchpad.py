"""The comp scratchpad: saved per member, paste a hull list, clear, and hand off to the comp editor."""

import re

from playwright.sync_api import expect

COMP_URL = re.compile(r"/comps/\d+$")


def test_scratchpad_saves_pastes_clears_and_moves_to_a_comp(login_as):
    theo = login_as("theorycrafter")
    page = theo.page
    page.goto("/scratchpad")
    expect(page.locator("#scratchpad-hulls option").first).to_be_attached()

    # Start clean whatever an earlier run left behind.
    if page.get_by_test_id("scratchpad.clear").is_enabled():
        page.once("dialog", lambda d: d.accept())
        page.get_by_test_id("scratchpad.clear").click()
    expect(page.get_by_test_id("scratchpad.slot.1.hull")).to_have_value("")

    # Two hulls typed by hand; Enter moves to the next row.
    first = page.get_by_test_id("scratchpad.slot.1.hull")
    first.fill("Astarte")
    first.press("Enter")
    expect(page.get_by_test_id("scratchpad.slot.2.hull")).to_be_focused()
    page.get_by_test_id("scratchpad.slot.2.hull").fill("Deacon")
    page.get_by_test_id("scratchpad.slot.2.hull").press("Enter")
    expect(page.get_by_test_id("scratchpad.eval.total")).to_contain_text("/ 200")

    # Leaving and coming back keeps them (saved on the server, so a reload is the hard case).
    page.wait_for_timeout(700)
    page.reload()
    expect(page.get_by_test_id("scratchpad.slot.1.hull")).to_have_value("Astarte")
    expect(page.get_by_test_id("scratchpad.slot.2.hull")).to_have_value("Deacon")

    # Paste by hand (the clipboard API is refused in a headless context, so the textarea opens).
    page.context.grant_permissions([])
    page.get_by_test_id("scratchpad.paste").click()
    box = page.get_by_test_id("scratchpad.paste.text")
    if box.count() == 0:  # the browser allowed the clipboard read; force the manual form
        page.evaluate("navigator.clipboard.readText = () => Promise.reject(new Error('denied'))")
        page.get_by_test_id("scratchpad.paste").click()
    box.fill("Astarte, Deacon\nKeres\nNot A Ship")
    page.get_by_test_id("scratchpad.paste.apply").click()
    expect(page.get_by_test_id("scratchpad.slot.1.hull")).to_have_value("Astarte")
    expect(page.get_by_test_id("scratchpad.slot.2.hull")).to_have_value("Deacon")
    expect(page.get_by_test_id("scratchpad.slot.3.hull")).to_have_value("Keres")
    expect(page.get_by_test_id("scratchpad.slot.4.hull")).to_have_value("")
    expect(page.get_by_test_id("scratchpad.paste.unknown")).to_contain_text("Not A Ship")

    # Move to the comp editor: a construction comp with the same hulls.
    page.get_by_test_id("scratchpad.move").click()
    expect(page).to_have_url(COMP_URL)
    expect(page.get_by_test_id("comp.status.badge")).to_have_text("construction")
    expect(page.get_by_test_id("comp.slot.1.hull")).to_have_value("Astarte")
    expect(page.get_by_test_id("comp.slot.3.hull")).to_have_value("Keres")
    comp_url = page.url

    # The scratchpad still has its contents; Clear all empties it and the empty state is saved.
    page.goto("/scratchpad")
    expect(page.get_by_test_id("scratchpad.slot.3.hull")).to_have_value("Keres")
    page.once("dialog", lambda d: d.accept())
    page.get_by_test_id("scratchpad.clear").click()
    expect(page.get_by_test_id("scratchpad.slot.1.hull")).to_have_value("")
    page.wait_for_timeout(300)
    page.reload()
    expect(page.locator("#scratchpad-hulls option").first).to_be_attached()
    expect(page.get_by_test_id("scratchpad.slot.1.hull")).to_have_value("")

    # The hand-off comp is prefixed so the cleanup command removes it.
    comp_id = comp_url.rsplit("/", 1)[1]
    theo.api_call(
        "PATCH", f"/api/comps/{comp_id}", {"name": f"pw_scratch_{comp_id}", "reason": "pw"}
    )
