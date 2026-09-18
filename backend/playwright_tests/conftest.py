"""Browser tests against the running dev servers (`make run`). Log in through /auth/dev-login, one context per role."""

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import (
    APIRequestContext,
    APIResponse,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

BASE_URL = os.environ.get("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:5173")
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Reserved character ids; `playwright_cleanup` deletes everything in 900000001..900000099.
CHARACTER_IDS = {
    "admin": 900_000_001,
    "captain": 900_000_002,
    "theorycrafter": 900_000_003,
    "pilot": 900_000_004,
    "guest": 900_000_005,
    "viewer": 900_000_006,
}
SECOND_PILOT = 900_000_007
INVITEE_BASE = 900_000_010
ROLES = list(CHARACTER_IDS)

_counter = 0


def uniq(prefix: str) -> str:
    """Unique, cleanup-friendly name: pw_<prefix>_<run>_<n>."""
    global _counter
    _counter += 1
    return f"pw_{prefix}_{int(time.time() * 1000):x}_{_counter}"


@dataclass
class Session:
    page: Page
    context: BrowserContext
    api: APIRequestContext
    character_id: int
    role: str

    def api_call(self, method: str, url: str, data=None) -> APIResponse:
        """Unsafe methods need the CSRF cookie echoed as a header; login() sets that cookie."""
        token = next((c["value"] for c in self.context.cookies() if c["name"] == "csrftoken"), "")
        return self.api.fetch(url, method=method, data=data, headers={"X-CSRFToken": token})

    def json(self, url: str):
        resp = self.api.get(url)
        assert resp.ok, f"{url}: {resp.status} {resp.text()[:200]}"
        return resp.json()


def dev_login(context: BrowserContext, **params) -> APIResponse:
    return context.request.get("/auth/dev-login", params=params, max_redirects=0)


def open_as(
    browser: Browser, role: str, character_id: int | None = None, name: str | None = None
) -> Session:
    context = browser.new_context(base_url=BASE_URL)
    resp = dev_login(
        context,
        character_id=character_id or CHARACTER_IDS[role],
        name=name or f"PW {role}",
        role=role,
    )
    assert resp.status == 302, f"dev-login as {role} failed: {resp.status} {resp.text()[:200]}"
    return Session(
        context.new_page(), context, context.request, character_id or CHARACTER_IDS[role], role
    )


def join_as(browser: Browser, join_url: str, character_id: int, name: str) -> tuple[Session, bool]:
    """Admission through an invite link: /auth/join stores the token, dev-login without a role admits."""
    context = browser.new_context(base_url=BASE_URL)
    context.request.get(urlparse(join_url).path, max_redirects=0)
    resp = dev_login(context, character_id=character_id, name=name)
    return Session(
        context.new_page(), context, context.request, character_id, "pilot"
    ), resp.status == 302


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # The scrim page is desktop-only (four columns, ~1320px minimum); the default 1280 viewport squeezes it.
    return {
        **browser_context_args,
        "base_url": BASE_URL,
        "viewport": {"width": 1600, "height": 900},
    }


@pytest.fixture(scope="session", autouse=True)
def clean_database_and_check_servers(playwright: Playwright):
    """Wipe pw_ rows, then confirm the backend has what the specs assume."""
    subprocess.run(
        ["uv", "run", "--env-file", ".env", "python", "manage.py", "playwright_cleanup"],
        cwd=BACKEND_DIR,
        check=True,
        shell=sys.platform == "win32",
    )
    api = playwright.request.new_context(base_url=BASE_URL)
    try:
        login = api.get(
            "/auth/dev-login",
            params={"character_id": CHARACTER_IDS["admin"], "name": "PW admin", "role": "admin"},
            max_redirects=0,
        )
        assert login.status == 302, (
            f"dev-login failed ({login.status}); is `make run` up at {BASE_URL} with dev settings?"
        )
        rulesets = api.get("/api/rulesets").json()
        assert any(r["code"] == "ATXXII" and r["has_point_table"] for r in rulesets), (
            "ATXXII ruleset missing: run `manage.py import_ruleset --path fixtures/rulesets/atxxii.yaml`"
        )
        assert api.get("/api/me").json()["team"]["active_ruleset"], "no active ruleset on the team"
    finally:
        api.dispose()


@pytest.fixture
def login_as(browser: Browser):
    """`login_as("pilot")` opens a fresh browser context logged in as that role; closed at teardown."""
    opened: list[Session] = []

    def _open(role: str) -> Session:
        session = open_as(browser, role)
        opened.append(session)
        return session

    yield _open
    for s in opened:
        s.context.close()
