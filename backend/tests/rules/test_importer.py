import pytest

from apps.core.importing import ImportFailed, ImportReport
from apps.rules import adapters
from apps.rules.engine import evaluate_comp
from apps.rules.exporter import export_ruleset
from apps.rules.importer import import_ruleset
from apps.rules.models import (
    MappingSource,
    PointTableVersion,
    Ruleset,
    RulesetShip,
    ShipClass,
    Tournament,
)
from apps.rules.yaml_io import load_ruleset_document
from apps.sde.models import EveType

from .conftest import MINI_ATXXII
from .engine import atxxii as at

pytestmark = pytest.mark.django_db


def test_import_counts_and_inference(imported_atxxii):
    ruleset, report = imported_atxxii
    assert report.ok
    assert report.derived["ship_classes"] == 11 and report.derived["stages"] == 2
    # 10 explicit + Zealot, Augoror Navy Issue, Keres inferred from hull-prefixed classes
    assert report.derived["ships"] == 13 and report.derived["ships_inferred"] == 3
    zealot = RulesetShip.objects.get(ruleset=ruleset, ship__name="Zealot")
    assert zealot.mapping_source == MappingSource.INFERRED_PREFIX
    assert (
        zealot.ship_class is not None and zealot.ship_class.name == "Zealot (Heavy Assault Cruiser)"
    )
    assert zealot.hull_size == "CR"
    augoror = RulesetShip.objects.get(ruleset=ruleset, ship__name="Augoror")
    assert augoror.hull_size == "LC" and not augoror.hull_size_is_override
    assert RulesetShip.objects.get(ruleset=ruleset, ship__name="Rattlesnake").is_unique
    assert (
        RulesetShip.objects.get(ruleset=ruleset, ship__name="Bhaalgorn").flagship_eligible is False
    )
    version = PointTableVersion.objects.get(ruleset=ruleset, purpose="cost")
    assert version.is_current and version.version_no == 1 and version.entries.count() == 11
    assert ruleset.module_rules.count() == 3 and ruleset.revision >= 1


def test_reimport_unchanged_writes_nothing(imported_atxxii, mini_doc):
    ruleset, _ = imported_atxxii
    revision, imported_at = ruleset.revision, ruleset.imported_at
    report = ImportReport(source="again")
    import_ruleset(mini_doc, report=report)
    ruleset.refresh_from_db()
    assert ruleset.revision == revision and ruleset.imported_at == imported_at
    assert any("unchanged" in w for w in report.warnings)


def test_changed_points_create_a_new_version(imported_atxxii):
    ruleset, _ = imported_atxxii
    doc = load_ruleset_document(
        MINI_ATXXII.replace(
            "name: Command Ship, size: BC, points: 33", "name: Command Ship, size: BC, points: 35"
        )
    )
    report = ImportReport(source="rev2")
    import_ruleset(doc, report=report)
    versions = list(
        PointTableVersion.objects.filter(ruleset=ruleset, purpose="cost").order_by("version_no")
    )
    assert [v.version_no for v in versions] == [1, 2]
    assert versions[1].is_current and not versions[0].is_current
    assert versions[0].entries.count() == 11  # history kept
    assert any("new version 2" in w for w in report.warnings)


def test_replace_points_rewrites_in_place(imported_atxxii):
    ruleset, _ = imported_atxxii
    doc = load_ruleset_document(MINI_ATXXII.replace("points: 33", "points: 34"))
    import_ruleset(doc, report=ImportReport(source="fix"), replace_points=True)
    assert PointTableVersion.objects.filter(ruleset=ruleset).count() == 1
    inputs = adapters.engine_inputs_for(Ruleset.objects.get(pk=ruleset.pk))
    assert inputs.table.class_points["Command Ship"] == 34


def test_dropped_class_is_deactivated_not_deleted(imported_atxxii):
    ruleset, _ = imported_atxxii
    doc = load_ruleset_document(
        MINI_ATXXII.replace("  - { name: Frigate, size: FR, points: 3 }\n", "").replace(
            "  - { hull: Rifter, class: Frigate }\n", ""
        )
    )
    import_ruleset(doc, report=ImportReport(source="drop"))
    frigate = ShipClass.objects.get(ruleset=ruleset, name="Frigate")
    assert frigate.active is False
    assert not RulesetShip.objects.filter(ruleset=ruleset, ship__name="Rifter").exists()


def test_unknown_and_ambiguous_names_reported_together(tiny_sde):
    EveType.objects.create(id=999002, name="Rifter", group_id=25, published=True)  # a second Rifter
    doc = load_ruleset_document(
        MINI_ATXXII.replace(
            "- { hull: Maulus, class: Tech 1 Disruption Frigate }",
            "- { hull: Maulus Navy Deluxe, class: Tech 1 Disruption Frigate }",
        )
    )
    with pytest.raises(ImportFailed) as exc:
        import_ruleset(doc, report=ImportReport(source="bad"))
    message = str(exc.value)
    assert "unknown hull: 'Maulus Navy Deluxe'" in message and "ambiguous hull: 'Rifter'" in message
    assert not Tournament.objects.exists()


def test_case_insensitive_hull_match(tiny_sde):
    doc = load_ruleset_document(MINI_ATXXII.replace("hull: Rifter,", "hull: rifter,"))
    ruleset = import_ruleset(doc, report=ImportReport(source="case"))
    assert RulesetShip.objects.filter(ruleset=ruleset, ship__name="Rifter").exists()


def test_requires_sde(db):
    doc = load_ruleset_document(MINI_ATXXII)
    with pytest.raises(ImportFailed) as exc:
        import_ruleset(doc, report=ImportReport(source="nosde"))
    assert "import_sde" in exc.value.remediation


def test_dry_run_leaves_nothing(mini_doc):
    report = ImportReport(source="dry")
    import_ruleset(mini_doc, report=report, dry_run=True)
    assert not Tournament.objects.exists() and any("dry run" in w for w in report.warnings)


def test_unverified_over_verified_needs_force(imported_atxxii):
    doc = load_ruleset_document(
        MINI_ATXXII.replace("schema_version: 1", "schema_version: 1\nverified: false\nnotes: draft")
    )
    with pytest.raises(ImportFailed):
        import_ruleset(doc, report=ImportReport(source="draft"))
    import_ruleset(doc, report=ImportReport(source="draft"), force=True)
    assert Tournament.objects.get(code="ATXXII").verified is False


def test_export_roundtrip_is_stable(imported_atxxii):
    ruleset, _ = imported_atxxii
    first = export_ruleset(ruleset)
    import_ruleset(load_ruleset_document(first), report=ImportReport(source="rt"))
    second = export_ruleset(Ruleset.objects.get(pk=ruleset.pk))
    assert first == second
    assert "flagship_eligible: false" in first and first.count("flagship_eligible") == 1
    assert "unique_hulls:\n- Rattlesnake" in first
    assert (
        "- {hull: Zealot, class: Zealot (Heavy Assault Cruiser)}" in first
    )  # inferred rows exported explicitly


def test_adapters_score_of99_and_cache_invalidates(imported_atxxii):
    ruleset, _ = imported_atxxii
    inputs = adapters.engine_inputs_for(ruleset)
    result = evaluate_comp(inputs.spec, inputs.table, inputs.hulls, at.slots(*at.OF99_SET1))
    assert result.total_points == 200 and result.is_legal
    assert inputs.hulls[at.BHAALGORN].flagship_eligible is False
    assert (
        inputs.hulls[at.RATTLESNAKE].flagship_eligible is True
        and inputs.hulls[at.RATTLESNAKE].is_unique
    )
    assert inputs.hulls[at.ASTARTE].flagship_eligible is False  # BC is not an eligible size
    assert adapters.engine_inputs_for(ruleset) is inputs
    ruleset.hull_sizes.filter(hull_size="BS").update(max_per_comp=3)
    ruleset.hull_sizes.get(hull_size="BC").save()  # signal bumps revision
    fresh = Ruleset.objects.get(pk=ruleset.pk)
    assert fresh.revision > ruleset.revision
    assert adapters.engine_inputs_for(fresh) is not inputs


def test_no_point_table_raises(tiny_sde):
    doc = load_ruleset_document(
        MINI_ATXXII.replace(
            "point_table:\n  label: Test table\n  hull_overrides: []\n", "point_table: null\n"
        )
        .replace(", points: 53", "")
        .replace(", points: 33", "")
        .replace(", points: 25", "")
        .replace(", points: 21", "")
        .replace(", points: 19", "")
        .replace(", points: 18", "")
        .replace(", points: 15", "")
        .replace(", points: 12", "")
        .replace(", points: 10", "")
        .replace(", points: 7", "")
        .replace(", points: 3", "")
    )
    ruleset = import_ruleset(doc, report=ImportReport(source="nopoints"))
    with pytest.raises(adapters.NoPointTable):
        adapters.engine_inputs_for(ruleset)
