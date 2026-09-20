"""Admin-defined roles: the matrix page, a new role handed out by invite, and what it unlocks."""

import time

from playwright.sync_api import Browser, expect

from .conftest import INVITEE_BASE, join_as, uniq


def test_admin_defines_a_role_and_a_member_lives_by_it(login_as, browser: Browser):
    admin = login_as("admin")
    page = admin.page
    page.goto("/team/roles")

    # Seeded rows are there; the admin row is ticked everywhere and locked.
    expect(page.get_by_test_id("roles.row.admin.perm.manage_team")).to_be_checked()
    expect(page.get_by_test_id("roles.row.admin.perm.manage_team")).to_be_disabled()
    expect(page.get_by_test_id("roles.row.pilot.perm.fly")).to_be_checked()
    expect(page.get_by_test_id("roles.row.viewer.perm.rsvp")).not_to_be_checked()

    # A new role with two permissions.
    name = uniq("scout")
    page.get_by_test_id("roles.new.name").fill(name)
    page.get_by_test_id("roles.new.description").fill("watches and reads")
    page.get_by_test_id("roles.new.create").click()
    expect(page.get_by_test_id("toast").first).to_have_text("Role created")
    row = page.get_by_test_id(f"roles.row.{name}")
    expect(row).to_be_visible()
    row.get_by_test_id(f"roles.row.{name}.perm.view_scrims").click()
    expect(row.get_by_test_id(f"roles.row.{name}.perm.view_scrims")).to_be_checked()
    row.get_by_test_id(f"roles.row.{name}.perm.browse_library").click()
    expect(row.get_by_test_id(f"roles.row.{name}.perm.browse_library")).to_be_checked()

    # The Team page offers it for invites; a member joins with it.
    page.goto("/team")
    page.get_by_test_id("team.invites.role").select_option(name)
    note = uniq("invite")
    page.get_by_test_id("team.invites.note").fill(note)
    page.get_by_test_id("team.invites.create").click()
    invite = next(i for i in admin.json("/api/team/invites") if i["note"] == note)
    assert invite["role"] == name
    invitee, admitted = join_as(
        browser, invite["url"], INVITEE_BASE + 20 + int(time.time()) % 20, uniq("scout")
    )
    try:
        assert admitted
        invitee.page.goto("/")
        expect(invitee.page.get_by_test_id("shell.role")).to_have_text(name)
        expect(invitee.page.get_by_test_id("nav.scrims")).to_be_visible()
        expect(invitee.page.get_by_test_id("nav.comps")).to_be_visible()
        expect(invitee.page.get_by_test_id("nav.roles")).to_have_count(0)
        expect(invitee.page.get_by_test_id("nav.audit")).to_have_count(0)
        caps = invitee.json("/api/me")["capabilities"]
        assert caps["view_scrims"] and caps["browse_library"] and not caps["rsvp"]
        assert invitee.api_call("POST", "/api/team/roles", {"name": "x"}).status == 403

        # Taking browse_library away reaches the member on their next load.
        page.goto("/team/roles")
        page.get_by_test_id(f"roles.row.{name}.perm.browse_library").click()
        expect(page.get_by_test_id(f"roles.row.{name}.perm.browse_library")).not_to_be_checked()
        expect(page.get_by_test_id(f"roles.row.{name}.members")).to_have_text("1")
        invitee.page.reload()
        expect(invitee.page.get_by_test_id("nav.comps")).to_have_count(0)
        expect(invitee.page.get_by_test_id("nav.scrims")).to_be_visible()

        # Deleting the role moves its member to pilot.
        page.once("dialog", lambda d: d.accept("pilot"))
        page.get_by_test_id(f"roles.row.{name}.delete").click()
        expect(page.get_by_test_id("toast").first).to_have_text("Role deleted")
        expect(page.get_by_test_id(f"roles.row.{name}")).to_have_count(0)
        invitee.page.reload()
        expect(invitee.page.get_by_test_id("shell.role")).to_have_text("pilot")
    finally:
        invitee.context.close()
