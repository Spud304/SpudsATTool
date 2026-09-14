import pytest
from playwright.sync_api import expect


def test_admin_switches_the_season_and_comps_follow(login_as):
    admin = login_as("admin")
    rulesets = admin.json("/api/rulesets")
    if len(rulesets) < 2:
        pytest.skip("needs at least two rulesets imported")
    current = admin.json("/api/me")["team"]["active_ruleset"]
    other = next(r["code"] for r in rulesets if r["code"] != current)

    try:
        admin.page.goto("/comps")
        expect(admin.page.get_by_text(f"Comps · {current}")).to_be_visible()
        admin.page.get_by_test_id("shell.season").select_option(other)
        expect(admin.page.get_by_test_id("shell.season")).to_have_value(other)
        expect(admin.page.get_by_text(f"Comps · {other}")).to_be_visible()

        pilot = login_as("pilot")
        pilot.page.goto("/comps")
        expect(pilot.page.get_by_test_id("shell.season")).to_have_text(
            other
        )  # read-only for non-admins
        expect(pilot.page.get_by_text(f"Comps · {other}")).to_be_visible()
    finally:
        restore = admin.api_call("PATCH", "/api/team", {"active_ruleset": current})
        assert restore.status == 200, restore.text()
