import pytest

from apps.sde.jsonl import ZipSource
from apps.sde.loader import import_source
from apps.sde.models import EveCategory, EveFaction, EveGroup, EveType

from .conftest import BUILD

pytestmark = pytest.mark.django_db


@pytest.fixture
def imported(tiny_zip):
    with ZipSource(tiny_zip) as source:
        return import_source(source, build=BUILD)


def test_type_fields_map_from_sde_names(imported):
    rifter = EveType.objects.select_related("group__category", "faction", "meta_group", "race").get(
        pk=587
    )
    assert rifter.name == "Rifter"
    assert rifter.group.name == "Frigate" and rifter.group.category.name == "Ship"
    assert rifter.faction.name == "Minmatar Republic"
    assert rifter.meta_group.name == "Tech I" and rifter.race.name == "Minmatar"
    assert rifter.tech_level == 1 and rifter.meta_level == 0
    assert (
        rifter.mass == 1067000.0
        and rifter.packaged_volume == 2500.0
        and rifter.market_group_id == 64
    )
    assert rifter.published and not rifter.removed


def test_absent_fields_are_null(imported):
    badger = EveType.objects.get(pk=648)
    assert badger.tech_level is None and badger.faction is None and badger.mass is None
    assert badger.group.name == "Hauler"


def test_published_mirrors_ccp_separately_from_removed(imported):
    thing = EveType.objects.get(pk=999999)
    assert thing.published is False and thing.removed is False


def test_types_outside_wanted_categories_are_skipped(imported):
    assert not EveType.objects.filter(pk=3000).exists()
    assert EveCategory.objects.get(pk=99).name == "Station"
    assert EveGroup.objects.get(pk=500).category.pk == 99


def test_unknown_faction_is_nulled_with_warning(imported):
    assert EveType.objects.get(pk=600).faction is None
    assert any("unknown faction" in w for w in imported.warnings)
    assert EveFaction.objects.count() == 1


def test_group_flags_default_false(imported):
    hauler = EveGroup.objects.get(pk=28)
    assert hauler.anchorable is False and hauler.use_base_price is False
