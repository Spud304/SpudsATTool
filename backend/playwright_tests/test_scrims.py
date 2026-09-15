import re

from playwright.sync_api import expect

from .conftest import uniq


def test_scrim_night_from_creation_to_no_show(login_as):
    pilot = login_as("pilot")  # logging in as pilot+ puts them on the roster
    captain = login_as("captain")
    me = pilot.json("/api/me")
    pilot_row = next(p for p in pilot.json("/api/pilots") if p["user_id"] == me["user_id"])

    # Captain schedules tonight.
    title = uniq("scrim")
    captain.page.goto("/scrims")
    captain.page.get_by_test_id("scrims.new.title").fill(title)
    captain.page.get_by_test_id("scrims.new.opponent").select_option("new")
    captain.page.get_by_test_id("scrims.new.opponent.new").fill(uniq("opp"))
    captain.page.get_by_test_id("scrims.new.stage").select_option("bracket")
    captain.page.get_by_test_id("scrims.new.motd").fill("pw be on comms")
    captain.page.get_by_test_id("scrims.new.submit").click()
    expect(captain.page.get_by_test_id("scrim.header.title")).to_have_text(title)
    expect(captain.page.get_by_test_id("scrim.header.motd")).to_have_text("pw be on comms")
    scrim_id = int(captain.page.url.rstrip("/").rsplit("/", 1)[-1])
    item = f"dash.scrims.item.{scrim_id}"

    # Pilot answers from the dashboard: maybe needs a reason first.
    pilot.page.goto("/")
    expect(pilot.page.get_by_test_id(item)).to_contain_text(title)
    pilot.page.get_by_test_id(f"{item}.rsvp.maybe").click()
    expect(pilot.page.get_by_test_id(f"{item}.rsvp.needs-reason")).to_be_visible()
    expect(pilot.page.get_by_test_id(f"{item}.rsvp.current")).to_have_text("no answer")
    pilot.page.get_by_test_id(f"{item}.rsvp.reason").fill("pw late from work")
    pilot.page.get_by_test_id(f"{item}.rsvp.maybe").click()
    expect(pilot.page.get_by_test_id(f"{item}.rsvp.current")).to_have_text("maybe")

    # Captain's roll call shows the answer with its reason.
    captain.page.goto("/scrims")
    row = captain.page.get_by_test_id(f"scrims.row.{scrim_id}")
    expect(row.get_by_test_id(f"scrims.row.{scrim_id}.tally")).to_contain_text("1")
    row.get_by_test_id(f"scrims.row.{scrim_id}.rollcall").click()
    expect(row.get_by_test_id(f"scrims.row.{scrim_id}.rollcall.{pilot_row['id']}")).to_contain_text(
        "pw late from work"
    )

    # On the night: mark the pilot as a no-show, with a reason that lands in the audit log.
    captain.page.goto(f"/scrims/{scrim_id}")
    att = captain.page.get_by_test_id(f"scrim.attendance.row.{pilot_row['id']}")
    expect(att.get_by_test_id(f"scrim.attendance.row.{pilot_row['id']}.rsvp")).to_have_text("?")
    expect(att.get_by_test_id(f"scrim.attendance.row.{pilot_row['id']}.reason")).to_contain_text(
        "pw late from work"
    )
    captain.page.once("dialog", lambda dialog: dialog.accept("pw never showed"))
    att.get_by_test_id(f"scrim.attendance.row.{pilot_row['id']}.set.no_show").click()
    expect(att.get_by_test_id(f"scrim.attendance.row.{pilot_row['id']}.removed")).to_have_text(
        "no-show"
    )

    captain.page.goto("/team/audit")
    captain.page.get_by_test_id("audit.filter").fill("scrim.no_show_removed")
    expect(
        captain.page.get_by_test_id("audit.row").filter(has_text="pw never showed").first
    ).to_be_visible()

    # The pilot sees their own status on the scrim page too.
    pilot.page.goto(f"/scrims/{scrim_id}")
    expect(pilot.page.get_by_test_id("scrim.header.title")).to_have_text(title)
    expect(pilot.page.get_by_test_id("scrim.rsvp.current")).to_have_text("maybe")


def test_roster_lists_members_and_captain_adds_a_merc(login_as):
    captain = login_as("captain")
    captain.page.goto("/team/pilots")
    expect(
        captain.page.get_by_test_id(re.compile(r"^pilots\.row\.\d+\.name$")).filter(
            has_text="PW captain"
        )
    ).to_be_visible()

    merc = uniq("merc")
    captain.page.get_by_test_id("pilots.new.name").fill(merc)
    captain.page.get_by_test_id("pilots.new.merc").click()
    captain.page.get_by_test_id("pilots.new.create").click()
    row = captain.page.get_by_test_id(re.compile(r"^pilots\.row\.\d+$")).filter(has_text=merc)
    expect(row).to_be_visible()
    expect(row.get_by_test_id(re.compile(r"\.merc$"))).to_be_checked()

    captain.page.get_by_test_id("pilots.new.name").fill(merc.upper())
    captain.page.get_by_test_id("pilots.new.create").click()
    expect(captain.page.get_by_test_id("pilots.new.error")).to_contain_text("already")


def test_viewer_reads_scrims_but_cannot_schedule_or_rsvp(login_as):
    viewer = login_as("viewer")
    viewer.page.goto("/scrims")
    expect(viewer.page.get_by_test_id("scrims.upcoming")).to_be_visible()
    expect(viewer.page.get_by_test_id("scrims.new")).to_have_count(0)
    expect(viewer.page.get_by_test_id("nav.pilots")).to_have_count(0)
    assert (
        viewer.api_call(
            "POST", "/api/scrims", {"title": "x", "date": "2030-01-01T19:00:00Z"}
        ).status
        == 403
    )

    guest = login_as("guest")
    guest.page.goto("/")
    expect(guest.page.get_by_test_id("nav.scrims")).to_have_count(0)
    assert guest.api.get("/api/scrims").status == 403
