from django.db import migrations

from apps.library.constants import ARCHETYPE_SEED


def seed(apps, schema_editor):
    Archetype = apps.get_model("library", "Archetype")
    for order, (name, retired) in enumerate(ARCHETYPE_SEED):
        Archetype.objects.get_or_create(
            name=name, defaults={"is_retired": retired, "sort_order": order}
        )


class Migration(migrations.Migration):
    dependencies = [("library", "0002_comps")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
