from django.db import migrations

FLYING_ROLES = ("pilot", "theorycrafter", "captain", "admin")


def backfill(apps, schema_editor):
    """Members admitted before the roster existed get their pilot row here; later ones get it on admission."""
    Membership = apps.get_model("accounts", "Membership")
    Pilot = apps.get_model("scrims", "Pilot")
    for membership in Membership.objects.filter(
        status="active", role__in=FLYING_ROLES
    ).select_related("user"):
        user = membership.user
        if Pilot.objects.filter(user=user).exists():
            continue
        name = user.display_name or user.username
        unlinked = Pilot.objects.filter(name__iexact=name, user__isnull=True).first()
        if unlinked is not None:
            unlinked.user = user
            unlinked.save(update_fields=["user"])
            continue
        if Pilot.objects.filter(name__iexact=name).exists():
            name = f"{name} ({user.pk})"
        Pilot.objects.create(name=name, user=user)


class Migration(migrations.Migration):
    dependencies = [("scrims", "0002_seed_warp_labels"), ("accounts", "__first__")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
