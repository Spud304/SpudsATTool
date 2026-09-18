import re

import pytest
from playwright.sync_api import Page, expect

from .conftest import ROLES

ALL = ["home", "scratchpad", "points", "comps", "fits", "team", "audit"]
# Pilots see the library because Team.pilots_can_browse_library defaults to true.
VISIBLE = {
    "admin": ALL,
    "captain": ALL,
    "theorycrafter": ["home", "scratchpad", "points", "comps", "fits", "team"],
    "pilot": ["home", "scratchpad", "points", "comps", "fits", "team"],
    "guest": ["home", "scratchpad", "points", "team"],
    "viewer": ["home", "scratchpad", "points", "team"],
}


@pytest.mark.parametrize("role", ROLES)
def test_role_sees_the_right_navigation(login_as, role):
    page = login_as(role).page
    page.goto("/")
    expect(page.get_by_test_id("shell.role")).to_have_text(role)
    expect(page.get_by_test_id("shell.logout")).to_be_visible()
    for item in ALL:
        link = page.get_by_test_id(f"nav.{item}")
        if item in VISIBLE[role]:
            expect(link, f"{role} should see nav.{item}").to_be_visible()
        else:
            expect(link, f"{role} should not see nav.{item}").to_have_count(0)


def test_viewer_is_refused_on_the_fit_library(login_as):
    page = login_as("viewer").page
    page.goto("/fits")
    expect(page.get_by_text(re.compile("library browsing is not enabled"))).to_be_visible()


def test_pilot_is_refused_on_the_audit_log(login_as):
    page = login_as("pilot").page
    page.goto("/team/audit")
    expect(
        page.get_by_text(re.compile("requires captain, admin, or the leadership flag"))
    ).to_be_visible()


def test_anonymous_visitor_only_gets_the_login_button(page: Page):
    page.goto("/fits")
    expect(page.get_by_test_id("shell.login")).to_be_visible()
    expect(page.get_by_test_id("nav.fits")).to_have_count(0)
