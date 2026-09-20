import pytest

from apps.accounts.models import Membership, MembershipStatus
from apps.audit.models import AuditLog

from .conftest import ADMIN_ID

pytestmark = pytest.mark.django_db


def test_me_anonymous_reports_configuration(client, team):
    body = client.get("/api/me").json()
    assert body["authenticated"] is False and body["admins_configured"] is False


def test_dev_login_env_admin(client, team, admins, login_as):
    login_as(role=None)
    body = client.get("/api/me").json()
    assert body["membership"]["role"] == "admin" and body["capabilities"]["manage_members"]
    assert body["characters"][0]["is_main"] is True


def test_dev_login_denied_without_admission(client, team, admins, login_as):
    resp = login_as(character_id=2, name="Stranger", role=None)
    assert resp.status_code == 403 and b"not a member" in resp.content
    assert client.get("/api/me").json()["authenticated"] is False


def test_dev_login_disabled_outside_dev(client, team, settings):
    settings.DEV_LOGIN_ENABLED = False
    assert client.get("/auth/dev-login", {"character_id": 1}).status_code == 404


def test_member_management_flow(client, team, admins, login_as):
    login_as(role=None)  # env admin
    resp = client.post(
        "/api/team/invites",
        {"role": "pilot", "uses": 2, "expires_in_hours": 24, "note": "scrim night"},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    invite = resp.json()
    assert invite["url"].endswith(f"/auth/join/{invite['token']}")

    client.logout()
    assert client.get(f"/auth/join/{invite['token']}").status_code == 302
    login_as(character_id=2, name="Pilot", role=None)
    me = client.get("/api/me").json()
    assert me["membership"]["role"] == "pilot" and me["capabilities"]["score"] is True
    assert me["capabilities"]["manage_members"] is False
    assert client.get("/api/audit").status_code == 403
    assert client.get("/api/team/invites").status_code == 403
    assert client.get("/api/rulesets").status_code == 200  # rules endpoints open to members
    pilot_id = me["user_id"]

    client.logout()
    login_as(role=None)
    resp = client.patch(
        f"/api/team/members/{pilot_id}",
        {"role": "theorycrafter", "is_leadership": True, "reason": "runs comps"},
        content_type="application/json",
    )
    assert resp.status_code == 200 and resp.json()["role"] == "theorycrafter"
    assert AuditLog.objects.filter(action="membership.updated", reason="runs comps").exists()

    resp = client.delete(
        f"/api/team/members/{pilot_id}", {"reason": "left"}, content_type="application/json"
    )
    assert resp.status_code == 204
    assert Membership.objects.get(user_id=pilot_id).status == MembershipStatus.REMOVED
    assert client.get("/api/audit", {"action": "membership.removed"}).json()["count"] == 1


def test_last_admin_guard_and_role_ceilings(client, team, admins, login_as):
    login_as(role=None)
    me = client.get("/api/me").json()
    # The only admin demoting themselves: the self-change rule answers first (403); the last-admin
    # guard (409) stays behind it for any other path that could drop the final admin.
    assert (
        client.patch(
            f"/api/team/members/{me['user_id']}", {"role": "pilot"}, content_type="application/json"
        ).status_code
        == 403
    )
    client.logout()
    login_as(character_id=2, name="Cap", role="captain")
    assert (
        client.post(
            "/api/team/invites", {"role": "admin"}, content_type="application/json"
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/team/invites", {"role": "pilot"}, content_type="application/json"
        ).status_code
        == 201
    )


def test_members_cannot_change_their_own_role_or_status(client, team, admins, login_as):
    login_as(character_id=2, name="Cap", role="captain")
    me = client.get("/api/me").json()
    url = f"/api/team/members/{me['user_id']}"
    for body in ({"role": "pilot"}, {"status": "suspended"}):
        assert client.patch(url, body, content_type="application/json").status_code == 403
    assert client.delete(url, {"reason": "bye"}, content_type="application/json").status_code == 403
    # a note about yourself is fine
    resp = client.patch(url, {"note": "on holiday next week"}, content_type="application/json")
    assert resp.status_code == 200 and resp.json()["note"] == "on holiday next week"


def test_team_settings_admin_only(client, team, login_as):
    login_as(character_id=3, name="TC", role="theorycrafter")
    assert (
        client.patch(
            "/api/team", {"affiliation_grace_hours": 48}, content_type="application/json"
        ).status_code
        == 403
    )
    client.logout()
    login_as(character_id=ADMIN_ID, role="admin")
    resp = client.patch(
        "/api/team", {"affiliation_grace_hours": 48}, content_type="application/json"
    )
    assert resp.status_code == 200 and resp.json()["affiliation_grace_hours"] == 48
    assert AuditLog.objects.filter(action="team.updated").exists()


def test_rules_endpoints_need_login(client, team, login_as):
    assert client.get("/api/rulesets").status_code == 401
    login_as(character_id=3, name="Viewer", role="viewer")
    assert client.get("/api/rulesets").status_code == 403
