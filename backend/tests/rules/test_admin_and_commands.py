import pytest
from django.contrib.admin.sites import site
from django.core.management import CommandError, call_command
from django.urls import reverse

from apps.accounts.models import User
from apps.rules import models as rules_models
from apps.rules.models import Tournament
from tests.conftest import MINI_ATXXII

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    user = User.objects.create_superuser("admin", password="pw")
    client.force_login(user)
    return client


def test_admin_pages_render(admin_client, imported_atxxii):
    ruleset, _ = imported_atxxii
    registered = [m for m in site._registry if m.__module__ == rules_models.__name__]
    assert rules_models.Ruleset in registered and rules_models.RulesetShip in registered
    for model in registered:
        info = (model._meta.app_label, model._meta.model_name)
        assert admin_client.get(reverse(f"admin:{info[0]}_{info[1]}_changelist")).status_code == 200
        obj = model.objects.first()
        if obj is not None:
            assert (
                admin_client.get(
                    reverse(f"admin:{info[0]}_{info[1]}_change", args=[obj.pk])
                ).status_code
                == 200
            )


def test_export_action_returns_yaml(admin_client, imported_atxxii):
    ruleset, _ = imported_atxxii
    resp = admin_client.post(
        reverse("admin:rules_ruleset_changelist"),
        {"action": "export_yaml", "_selected_action": [ruleset.pk]},
    )
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/yaml")
    assert b"code: ATXXII" in resp.content


def test_import_and_export_commands(tiny_sde, tmp_path, capsys):
    path = tmp_path / "mini.yaml"
    path.write_text(MINI_ATXXII, encoding="utf-8")
    call_command("import_ruleset", "--path", str(path), "--dry-run")
    assert not Tournament.objects.exists()
    call_command("import_ruleset", "--path", str(path))
    assert Tournament.objects.filter(code="ATXXII").exists()
    out = tmp_path / "export.yaml"
    call_command("export_ruleset", "ATXXII", "--out", str(out))
    assert "tournament:" in out.read_text(encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("export_ruleset", "NOPE")
    with pytest.raises(CommandError):
        call_command("import_ruleset", "--path", str(tmp_path / "missing.yaml"))


def test_import_command_reports_schema_errors(tiny_sde, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(MINI_ATXXII.replace("point_cap: 200", "point_cap: many"), encoding="utf-8")
    with pytest.raises(CommandError) as exc:
        call_command("import_ruleset", "--path", str(path))
    assert "docs/rulesets.md" in str(exc.value)
