from django.db import migrations

from apps.scrims.constants import WARP_IN_LABELS


def seed(apps, schema_editor):
    WarpInLabel = apps.get_model("scrims", "WarpInLabel")
    for order, label in enumerate(WARP_IN_LABELS):
        WarpInLabel.objects.get_or_create(label=label, defaults={"sort_order": order})


class Migration(migrations.Migration):
    dependencies = [("scrims", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
