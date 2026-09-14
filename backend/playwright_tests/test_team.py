import re
import time

from playwright.sync_api import Browser, expect

from .conftest import INVITEE_BASE, join_as, uniq


def test_invite_link_admits_a_pilot_and_admin_manages_them(login_as, browser: Browser):
    admin = login_as("admin")
    admin.page.goto("/team")

    note = uniq("invite")
    admin.page.get_by_test_id("team.invites.role").select_option("pilot")
    admin.page.get_by_test_id("team.invites.note").fill(note)
    admin.page.get_by_test_id("team.invites.create").click()
    expect(
        admin.page.get_by_test_id(re.compile(r"team\.invites\.row\.")).filter(has_text=note)
    ).to_be_visible()

    invite = next(i for i in admin.json("/api/team/invites") if i["note"] == note)
    invitee, admitted = join_as(
        browser, invite["url"], INVITEE_BASE + int(time.time()) % 50, uniq("invitee")
    )
    try:
        assert admitted
        invitee.page.goto("/")
        expect(invitee.page.get_by_test_id("shell.role")).to_have_text("pilot")
        user_id = invitee.json("/api/me")["user_id"]

        admin.page.reload()
        row = admin.page.get_by_test_id(f"team.members.row.{user_id}")
        expect(row).to_be_visible()
        expect(
            row.get_by_test_id("team.members.remove")
        ).to_be_visible()  # controls appear once /api/me loads
        expect(row.get_by_test_id("team.members.role")).to_have_value("pilot")

        row.get_by_test_id("team.members.role").select_option("theorycrafter")
        expect(row.get_by_test_id("team.members.role")).to_have_value("theorycrafter")
        row.get_by_test_id(
            "team.members.leadership"
        ).click()  # controlled input: state lands after the PATCH
        expect(row.get_by_test_id("team.members.leadership")).to_be_checked()

        invitee.page.reload()
        expect(invitee.page.get_by_test_id("shell.role")).to_have_text("theorycrafter")
        expect(
            invitee.page.get_by_test_id("nav.audit")
        ).to_be_visible()  # leadership unlocks the audit log

        admin.page.once("dialog", lambda dialog: dialog.accept("pw no-show"))
        row.get_by_test_id("team.members.remove").click()
        expect(row.get_by_test_id("team.members.status")).to_have_text("removed")
        expect(row.get_by_test_id("team.members.reinstate")).to_be_visible()

        invitee.page.reload()
        expect(invitee.page.get_by_test_id("nav.fits")).to_have_count(
            0
        )  # removed members lose the library
    finally:
        invitee.context.close()

    admin.page.goto("/team/audit")
    admin.page.get_by_test_id("audit.filter").fill("membership.removed")
    expect(
        admin.page.get_by_test_id("audit.row").filter(has_text="pw no-show").first
    ).to_be_visible()


def test_admin_adds_toggles_and_deletes_an_admission_rule(login_as):
    admin = login_as("admin")
    admin.page.goto("/team")
    entity_id = 900_000_000 + int(time.time()) % 900_000
    admin.page.get_by_test_id("team.rules.kind").select_option("corporation")
    admin.page.get_by_test_id("team.rules.id").fill(str(entity_id))
    admin.page.get_by_test_id("team.rules.name").fill(uniq("corp"))
    admin.page.get_by_test_id("team.rules.role").select_option("pilot")
    admin.page.get_by_test_id("team.rules.add").click()

    row = admin.page.get_by_test_id(re.compile(r"team\.rules\.row\.")).filter(
        has_text=str(entity_id)
    )
    expect(row).to_be_visible()
    expect(row.get_by_test_id("team.rules.enabled")).to_be_checked()
    row.get_by_test_id(
        "team.rules.enabled"
    ).click()  # controlled input: state lands after the PATCH
    expect(row.get_by_test_id("team.rules.enabled")).not_to_be_checked()
    row.get_by_test_id("team.rules.delete").click()
    expect(row).to_have_count(0)


def test_captain_manages_members_but_cannot_grant_admin(login_as):
    captain = login_as("captain")
    captain.page.goto("/team")
    expect(captain.page.get_by_test_id("team.invites")).to_be_visible()
    options = captain.page.get_by_test_id("team.invites.role").locator("option").all_text_contents()
    assert "admin" not in options

    pilot = login_as("pilot")
    pilot.page.goto("/team")
    expect(pilot.page.get_by_test_id("team.invites")).to_have_count(0)
    expect(pilot.page.get_by_test_id("team.members.remove")).to_have_count(0)
