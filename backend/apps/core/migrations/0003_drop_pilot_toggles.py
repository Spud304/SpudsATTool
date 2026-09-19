"""The two pilot toggles now live on the pilot role's permission set (accounts 0002 copied them)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_team_active_ruleset"),
        ("accounts", "0002_roles"),
    ]

    operations = [
        migrations.RemoveField("team", "pilots_can_score"),
        migrations.RemoveField("team", "pilots_can_browse_library"),
    ]
