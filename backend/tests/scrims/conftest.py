from dataclasses import replace
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.accounts import services as account_services
from apps.accounts.models import Role, User
from apps.accounts.sso import SsoIdentity
from apps.library import comps
from apps.library import services as fit_services
from apps.library.comps import SlotPatch
from apps.scrims import broker, sessions
from tests.conftest import ABSO_FIT, ABSO_PYFA
from tests.rules.engine import atxxii as at


def make_member(character_id: int, name: str, role: str) -> User:
    """A logged-in-once member with an active membership (and, for pilot+, a roster pilot)."""
    identity = SsoIdentity(
        character_id=character_id, name=name, owner_hash="o", scopes=("publicData",)
    )
    character = account_services.upsert_character(identity, None)
    user = account_services.ensure_user(character)
    account_services._set_membership(user, role=role, source="explicit", note="test")
    return user


@pytest.fixture(autouse=True)
def fresh_broker_and_cache():
    broker.reset_broker()
    cache.clear()
    yield
    broker.reset_broker()


@pytest.fixture
def captain(db):
    return make_member(101, "Cap", Role.CAPTAIN)


@pytest.fixture
def theo(db):
    return make_member(104, "Theo", Role.THEORYCRAFTER)


@pytest.fixture
def pilot(db):
    return make_member(102, "Pilot One", Role.PILOT)


@pytest.fixture
def viewer(db):
    return make_member(103, "Watcher", Role.VIEWER)


@pytest.fixture
def tonight():
    return timezone.now() + timedelta(hours=3)


@pytest.fixture
def scrim(imported_atxxii, captain, pilot, tonight):
    """A bracket-stage session for tonight: 4 bans per side, Bo3 with avalanche 2/1."""
    return sessions.create_session(captain, title="OF 99", date=tonight, stage_code="bracket")


def of99_slots(overrides: dict | None = None) -> list[SlotPatch]:
    overrides = overrides or {}
    return [
        replace(SlotPatch(slot_no=i, type_id=type_id), **overrides.get(i, {}))
        for i, type_id in enumerate(at.OF99_SET1, start=1)
    ]


@pytest.fixture
def abso_fit(library_sde, imported_atxxii, theo):
    return fit_services.create_fit(theo, eft_text=ABSO_FIT, pyfa_summary=ABSO_PYFA, status="active")


@pytest.fixture
def of99_comp(abso_fit, theo):
    """The sheet's OF 99 set-1 comp, slot 3 carrying a default fit, a ship note and a link script."""
    comp = comps.create_comp(theo, name="Armor Rush", status="active")
    comps.update_comp(
        theo,
        comp,
        slots=of99_slots(
            {
                3: {
                    "default_fit_id": abso_fit.pk,
                    "ship_note": "info bursts",
                    "link_scripts": ("AE",),
                }
            }
        ),
    )
    return comp
