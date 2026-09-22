"""Django admin access becomes env admins only (ADMIN_CHARACTER_IDS). Team admins made before this
kept is_staff/is_superuser forever, even after a demotion. Users with no membership (createsuperuser)
are left alone."""

from django.conf import settings
from django.db import migrations


def clear_non_env_admins(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    env_ids = list(settings.ADMIN_CHARACTER_IDS)
    keep = User.objects.filter(
        membership__status="active",
        membership__role__is_system=True,
        characters__character_id__in=env_ids,
    ).values("pk")
    User.objects.filter(membership__isnull=False).exclude(pk__in=keep).update(
        is_staff=False, is_superuser=False
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_roles")]

    operations = [migrations.RunPython(clear_non_env_admins, migrations.RunPython.noop)]
