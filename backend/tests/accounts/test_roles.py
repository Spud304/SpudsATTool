"""Roles as data: seeded defaults, effective permissions, the admin's edits, and their reach."""

import json

import pytest
from django.utils import timezone

from apps.accounts import permissions, roles
from apps.accounts.models import Invite, Membership, Role, TeamRole
from apps.audit.models import AuditLog
from apps.scrims.models import Pilot

from .conftest import ADMIN_ID

pytestmark = pytest.mark.django_db
JSON = "application/json"


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type=JSON)


def patch(client, url, body):
    return client.patch(url, json.dumps(body), content_type=JSON)


def test_defaults_are_seeded_and_match_the_old_ranks(team):
    slugs = list(TeamRole.objects.order_by("sort_order").values_list("slug", flat=True))
    assert slugs == ["admin", "captain", "theorycrafter", "pilot", "guest", "viewer"]
    admin = roles.by_slug(Role.ADMIN)
    assert admin.is_system and admin.grants("manage_team") and admin.grants("view_assigned_scrims")
    pilot = roles.by_slug("pilot")
    assert {"view_scrims", "rsvp", "fly", "score", "browse_library", "suggest_library"} <= set(
        pilot.permissions
    )
    assert not pilot.grants("edit_sets") and not pilot.grants("manage_members")
    guest = roles.by_slug("guest")
    assert set(guest.permissions) == {"view_assigned_scrims", "fly"}
    assert roles.by_slug("viewer").permissions == ["view_scrims"]
    assert set(roles.by_slug("captain").permissions) >= {"manage_scrims", "manage_members"}
    assert "manage_team" not in roles.by_slug("captain").permissions


def test_effective_permissions_follow_role_and_leadership(team, client, login_as):
    login_as(character_id=21, name="Watcher", role="viewer")
    me = client.get("/api/me").json()
    caps = me["capabilities"]
    assert caps["view_scrims"] and not caps["rsvp"] and not caps["is_admin"]
    assert set(caps) == permissions.PERMISSION_CODES | {"is_admin"}
    membership = Membership.objects.get(user_id=me["user_id"])
    membership.is_leadership = True
    membership.save()
    caps = client.get("/api/me").json()["capabilities"]
    assert caps["view_audit"] and caps["view_pilot_notes"] and not caps["manage_members"]


def test_admin_creates_a_role_and_its_members_follow(team, admins, client, login_as):
    login_as(role=None)  # the env admin
    listing = client.get("/api/team/roles").json()
    assert {r["slug"] for r in listing["roles"]} >= {"admin", "pilot"}
    assert {c["code"] for c in listing["catalog"]} == permissions.PERMISSION_CODES
    resp = post(
        client,
        "/api/team/roles",
        {
            "name": "Scout",
            "description": "watches",
            "permissions": ["view_scrims", "browse_library"],
        },
    )
    assert resp.status_code == 201, resp.content
    scout = resp.json()
    assert scout["slug"] == "scout" and scout["permissions"] == ["browse_library", "view_scrims"]
    assert AuditLog.objects.filter(action="role.created").exists()

    # a member on the new role gets exactly those permissions
    client.post("/auth/logout")
    login_as(character_id=31, name="Eyes", role="scout")
    caps = client.get("/api/me").json()["capabilities"]
    assert caps["view_scrims"] and caps["browse_library"] and not caps["rsvp"] and not caps["fly"]
    assert client.get("/api/comps").status_code == 200
    assert client.get("/api/team/roles").status_code == 200  # any member may read the list
    assert post(client, "/api/team/roles", {"name": "x"}).status_code == 403
    assert Pilot.objects.filter(user__characters__character_id=31).count() == 0

    # granting fly creates the roster row for current members
    client.post("/auth/logout")
    login_as(role=None)
    resp = patch(
        client,
        f"/api/team/roles/{scout['id']}",
        {"permissions": ["view_scrims", "browse_library", "fly"], "reason": "scouts fly too"},
    )
    assert resp.status_code == 200 and "fly" in resp.json()["permissions"]
    assert Pilot.objects.filter(user__characters__character_id=31).count() == 1
    assert AuditLog.objects.filter(action="role.updated", reason="scouts fly too").exists()

    # unknown codes and duplicate names are refused
    assert (
        patch(client, f"/api/team/roles/{scout['id']}", {"permissions": ["teleport"]}).status_code
        == 422
    )
    assert post(client, "/api/team/roles", {"name": "scout"}).status_code == 409


def test_system_role_is_protected(team, admins, client, login_as):
    login_as(role=None)
    admin = roles.admin_role()
    assert (
        patch(client, f"/api/team/roles/{admin.pk}", {"permissions": ["view_scrims"]}).status_code
        == 409
    )
    assert (
        patch(client, f"/api/team/roles/{admin.pk}", {"description": "the boss"}).status_code == 200
    )
    assert client.delete(f"/api/team/roles/{admin.pk}").status_code == 409
    # every code shows as granted, whatever is stored
    row = next(r for r in client.get("/api/team/roles").json()["roles"] if r["slug"] == "admin")
    assert set(row["permissions"]) == permissions.PERMISSION_CODES


def test_delete_reassigns_members_invites_and_rules(team, admins, client, login_as):
    login_as(role=None)
    scout = roles.create_role(None, name="Scout", permissions=["view_scrims"])
    pilot = roles.by_slug("pilot")
    client.post("/auth/logout")
    login_as(character_id=41, name="Eyes", role="scout")
    client.post("/auth/logout")
    login_as(role=None)
    Invite.objects.create(role=scout, expires_at=timezone.now())
    assert client.delete(f"/api/team/roles/{scout.pk}").status_code == 409  # in use, no target
    assert client.delete(f"/api/team/roles/{scout.pk}?reassign_to={pilot.pk}").status_code == 204
    assert Membership.objects.get(user__characters__character_id=41).role == pilot
    assert Invite.objects.get().role == pilot
    assert not TeamRole.objects.filter(slug="scout").exists()
    assert AuditLog.objects.filter(action="role.deleted").exists()


def test_manage_members_assigns_any_role_but_admin(team, admins, client, login_as):
    login_as(role=None)
    roles.create_role(None, name="Scout", permissions=["view_scrims"])
    client.post("/auth/logout")
    login_as(character_id=2, name="Cap", role="captain")
    assert post(client, "/api/team/invites", {"role": "scout"}).status_code == 201
    assert post(client, "/api/team/invites", {"role": "admin"}).status_code == 403
    assert post(client, "/api/team/invites", {"role": "nope"}).status_code == 422
    client.post("/auth/logout")
    login_as(character_id=ADMIN_ID, role="admin")
    assert post(client, "/api/team/invites", {"role": "admin"}).status_code == 201


def test_assigned_only_member_lists_just_their_scrims(team, admins, client, login_as):
    login_as(character_id=51, name="Merc", role="guest")
    assert client.get("/api/scrims").json() == []
    assert client.get("/api/team").status_code == 200  # any member reads the team brief
    assert client.get("/api/rulesets").status_code == 403  # no browse_library


def test_deleting_a_role_cannot_move_its_members_into_admin(team, admins, client, login_as):
    ops = TeamRole.objects.create(slug="ops", name="Ops", permissions=["manage_team"])
    login_as(character_id=41, name="Ops Lead", role="ops")
    admin_id = roles.by_slug(Role.ADMIN).pk
    resp = client.delete(f"/api/team/roles/{ops.pk}?reassign_to={admin_id}")
    assert resp.status_code == 403, resp.content
    assert Membership.objects.get(user__characters__character_id=41).role == ops
    viewer_id = roles.by_slug("viewer").pk
    assert client.delete(f"/api/team/roles/{ops.pk}?reassign_to={viewer_id}").status_code == 204


def test_members_cannot_set_their_own_leadership_flag(team, client, login_as):
    login_as(character_id=42, name="Cap", role="captain")
    me = client.get("/api/me").json()
    resp = patch(client, f"/api/team/members/{me['user_id']}", {"is_leadership": True})
    assert resp.status_code == 403
    assert not Membership.objects.get(user_id=me["user_id"]).is_leadership
