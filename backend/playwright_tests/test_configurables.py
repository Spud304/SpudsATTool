"""Configurables: archetypes and warp-in labels reach the pickers; opponents moved here from Pilots."""

from playwright.sync_api import expect

from .conftest import uniq


def test_archetype_and_warp_label_reach_the_pickers(login_as):
    admin = login_as("admin")
    page = admin.page
    page.goto("/team/configurables")
    expect(page.get_by_test_id("opponents")).to_be_visible()

    # an archetype, then it is offered in the comp builder
    name = uniq("arch")
    page.get_by_test_id("config.archetypes.new.name").fill(name)
    page.get_by_test_id("config.archetypes.new.create").click()
    expect(page.get_by_test_id("toast").first).to_have_text("Archetype added")
    comp = admin.api_call(
        "POST", "/api/comps", {"name": uniq("comp"), "notes": "", "ban_theory": ""}
    ).json()
    page.goto(f"/comps/{comp['id']}")
    expect(page.get_by_test_id("comp.archetype").locator("option", has_text=name)).to_have_count(1)

    # retire it and it leaves the picker
    page.goto("/team/configurables")
    arch = next(a for a in admin.json("/api/comps/vocab")["archetypes"] if a["name"] == name)
    page.get_by_test_id(
        f"config.archetypes.row.{arch['id']}.retired"
    ).click()  # controlled: state lands after the PATCH
    expect(page.get_by_test_id(f"config.archetypes.row.{arch['id']}.retired")).to_be_checked()
    expect(page.get_by_test_id("toast").first).to_have_text("Archetype saved")
    page.goto(f"/comps/{comp['id']}")
    expect(page.get_by_test_id("comp.archetype").locator("option", has_text=name)).to_have_count(0)

    # a warp label reaches a set's warp-call select
    label = uniq("wl")
    page.goto("/team/configurables")
    page.get_by_test_id("config.warp.new.label").fill(label)
    page.get_by_test_id("config.warp.new.create").click()
    expect(page.get_by_test_id("toast").first).to_have_text("Label added")
    assert label in admin.json("/api/scrims/vocab")["warp_labels"]
    labels = admin.json("/api/warp-labels")
    mine = next(r for r in labels if r["label"] == label)
    assert (
        admin.api_call("PATCH", f"/api/warp-labels/{mine['id']}", {"is_active": False}).status
        == 200
    )
    assert label not in admin.json("/api/scrims/vocab")["warp_labels"]
    assert admin.api_call("DELETE", f"/api/warp-labels/{mine['id']}").status == 204

    # a theorycrafter sees archetypes but not warp labels or opponents
    theo = login_as("theorycrafter")
    theo.page.goto("/team/configurables")
    expect(theo.page.get_by_test_id("config.archetypes")).to_be_visible()
    expect(theo.page.get_by_test_id("config.warp")).to_have_count(0)
    expect(theo.page.get_by_test_id("opponents")).to_have_count(0)
