import json

import pytest

from apps.audit.models import AuditLog
from apps.core.models import Team
from apps.rules import selection
from apps.rules.importer import import_ruleset
from apps.rules.yaml_io import load_ruleset_document
from tests.conftest import ABSO_FIT, MINI_ATXXII

pytestmark = pytest.mark.django_db


def test_import_sets_active_when_unset(imported_atxxii):
    ruleset, report = imported_atxxii
    team = Team.get_solo()
    assert team.active_ruleset_id == ruleset.pk
    assert any("active ruleset" in w for w in report.warnings)
    active = selection.active_ruleset()
    assert active is not None and active.pk == ruleset.pk


def test_fallback_when_unset(imported_atxxii):
    ruleset, _ = imported_atxxii
    Team.objects.update(active_ruleset=None)
    active = selection.active_ruleset()
    assert active is not None and active.pk == ruleset.pk
    assert selection.fallback_ruleset() is not None


def test_no_rulesets(db):
    assert selection.active_ruleset() is None


def test_team_patch_admin_only_and_me(client, library_sde, imported_atxxii, login_as):
    from apps.core.importing import ImportReport

    other = load_ruleset_document(
        MINI_ATXXII.replace("code: ATXXII", "code: ATX2").replace("year: 2026", "year: 2025")
    )
    import_ruleset(other, report=ImportReport(source="mini2"))

    login_as(role="pilot")
    assert client.get("/api/me").json()["team"]["active_ruleset"] == "ATXXII"
    resp = client.patch(
        "/api/team", json.dumps({"active_ruleset": "ATX2"}), content_type="application/json"
    )
    assert resp.status_code == 403
    client.get("/auth/logout")

    login_as(character_id=9, name="Boss", role="admin")
    resp = client.patch(
        "/api/team", json.dumps({"active_ruleset": "ATX2"}), content_type="application/json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["active_ruleset"] == "ATX2" and not resp.json()["active_ruleset_is_fallback"]
    assert client.get("/api/me").json()["team"]["active_ruleset"] == "ATX2"
    entry = AuditLog.objects.get(action="team.updated")
    assert entry.before == {"active_ruleset": "ATXXII"} and entry.after == {
        "active_ruleset": "ATX2"
    }
    resp = client.patch(
        "/api/team", json.dumps({"active_ruleset": "NOPE"}), content_type="application/json"
    )
    assert resp.status_code == 422
    resp = client.patch(
        "/api/team", json.dumps({"active_ruleset": None}), content_type="application/json"
    )
    assert resp.status_code == 200 and resp.json()["active_ruleset_is_fallback"]


def test_fit_legality_defaults_to_active(client, library_sde, imported_atxxii, login_as):
    login_as(role="pilot")
    fit_id = client.post(
        "/api/fits", json.dumps({"eft_text": ABSO_FIT}), content_type="application/json"
    ).json()["id"]
    body = client.get(f"/api/fits/{fit_id}/legality").json()
    assert body["ruleset"] == "ATXXII"
