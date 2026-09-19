"""Roles become rows with a permission set. The six shipped roles are seeded and every
membership, invite and admission rule is pointed at its row; the pilot role takes the team's
two old toggles (pilots can score, pilots can browse the library) so nothing changes on upgrade."""

import django.db.models.deletion
from django.db import migrations, models

import apps.accounts.models


def seed_and_link(apps, schema_editor):
    from apps.accounts.roles import default_definitions

    TeamRole = apps.get_model("accounts", "TeamRole")
    Team = apps.get_model("core", "Team")
    team = Team.objects.order_by("id").first()
    toggles = {}
    if team is not None:
        toggles = {
            "pilots_can_score": team.pilots_can_score,
            "pilots_can_browse": team.pilots_can_browse_library,
        }
    by_slug = {}
    for definition in default_definitions(**toggles):
        slug = definition.pop("slug")
        by_slug[slug], _ = TeamRole.objects.get_or_create(slug=slug, defaults=definition)
    for model_name, old_field, new_field in (
        ("Membership", "role_code", "role"),
        ("Invite", "role_code", "role"),
        ("AdmissionRule", "default_role_code", "default_role"),
    ):
        Model = apps.get_model("accounts", model_name)
        for row in Model.objects.all():
            code = getattr(row, old_field)
            setattr(row, new_field, by_slug.get(code) or by_slug["pilot"])
            row.save(update_fields=[new_field])


def unlink(apps, schema_editor):
    for model_name, old_field, new_field in (
        ("Membership", "role_code", "role"),
        ("Invite", "role_code", "role"),
        ("AdmissionRule", "default_role_code", "default_role"),
    ):
        Model = apps.get_model("accounts", model_name)
        for row in Model.objects.select_related(new_field):
            setattr(row, old_field, getattr(row, new_field).slug)
            row.save(update_fields=[old_field])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("core", "0002_team_active_ruleset"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeamRole",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("slug", models.SlugField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=60, unique=True)),
                ("description", models.CharField(blank=True, max_length=200)),
                ("permissions", models.JSONField(default=list)),
                ("is_system", models.BooleanField(default=False)),
                ("sort_order", models.SmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "accounts_role", "ordering": ["sort_order", "name"]},
        ),
        # keep the old strings under a temporary name while the rows are linked
        migrations.RenameField("membership", "role", "role_code"),
        migrations.RenameField("invite", "role", "role_code"),
        migrations.RenameField("admissionrule", "default_role", "default_role_code"),
        migrations.AddField(
            model_name="membership",
            name="role",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="memberships",
                to="accounts.teamrole",
            ),
        ),
        migrations.AddField(
            model_name="invite",
            name="role",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invites",
                to="accounts.teamrole",
            ),
        ),
        migrations.AddField(
            model_name="admissionrule",
            name="default_role",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="admission_rules",
                to="accounts.teamrole",
            ),
        ),
        migrations.RunPython(seed_and_link, unlink),
        migrations.RemoveField("membership", "role_code"),
        migrations.RemoveField("invite", "role_code"),
        migrations.RemoveField("admissionrule", "default_role_code"),
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.ForeignKey(
                default=apps.accounts.models.default_role_pk,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="memberships",
                to="accounts.teamrole",
            ),
        ),
        migrations.AlterField(
            model_name="invite",
            name="role",
            field=models.ForeignKey(
                default=apps.accounts.models.default_role_pk,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invites",
                to="accounts.teamrole",
            ),
        ),
        migrations.AlterField(
            model_name="admissionrule",
            name="default_role",
            field=models.ForeignKey(
                default=apps.accounts.models.default_role_pk,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="admission_rules",
                to="accounts.teamrole",
            ),
        ),
    ]
