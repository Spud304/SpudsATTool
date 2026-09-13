import pytest

from apps.rules import yaml_io
from apps.rules.yaml_io import DocumentInvalid, dump_document, load_ruleset_document

from .conftest import MINI_ATXXII


def test_mini_document_loads():
    doc = load_ruleset_document(MINI_ATXXII)
    assert doc.tournament.code == "ATXXII" and len(doc.ship_classes) == 11
    assert doc.ruleset.flagship.eligible_meta_groups == ["Tech I", "Tech II", "Faction"]
    assert doc.stages[1].avalanche is not None and doc.stages[1].avalanche.blind is True


def test_all_problems_reported_at_once():
    bad = MINI_ATXXII.replace("ban_order: ABBAAB }", "ban_order: ABBA }")
    bad = bad.replace(
        "- { hull: Rifter, class: Frigate }",
        "- { hull: Rifter, class: Frigate }\n  - { hull: Rifter, class: Frigate }",
    )
    bad = bad.replace(
        "- { size: FLAG, label: Flagship, max_per_comp: 1 }",
        "- { size: FLAG, label: Flagship, max_per_comp: 1, duplicate_surcharge: 2 }",
    )
    with pytest.raises(DocumentInvalid) as exc:
        load_ruleset_document(bad)
    message = str(exc.value)
    assert "stages[0].ban_order" in message
    assert "'Rifter' listed more than once" in message
    assert "FLAG" in message and "duplicate_surcharge" in message
    assert message.startswith("3 problem(s)")


def test_unknown_key_and_wrong_type_report_paths():
    bad = MINI_ATXXII.replace("point_cap: 200", "point_cap: lots\n  bogus: 1")
    with pytest.raises(DocumentInvalid) as exc:
        load_ruleset_document(bad)
    assert "ruleset.point_cap" in str(exc.value) and "ruleset.bogus" in str(exc.value)


def test_duplicate_yaml_key_rejected():
    with pytest.raises(DocumentInvalid) as exc:
        load_ruleset_document(
            MINI_ATXXII.replace("schema_version: 1", "schema_version: 1\nschema_version: 1")
        )
    assert "duplicate key" in str(exc.value)


def test_kill_table_requires_matching_source():
    with pytest.raises(DocumentInvalid) as exc:
        load_ruleset_document(MINI_ATXXII + "kill_table: { classes: [] }\n")
    assert "kill_table" in str(exc.value)


def test_flag_row_required_only_with_exemption():
    without = MINI_ATXXII.replace("  - { size: FLAG, label: Flagship, max_per_comp: 1 }\n", "")
    with pytest.raises(DocumentInvalid):
        load_ruleset_document(without)
    disabled = (
        without.replace("flagship: { enabled: true }", "flagship: { enabled: false }")
        .replace(", flagship_uses: 1", "")
        .replace(
            "  flagship: { allowed_meta_groups: [Tech I, Tech II, Faction, Deadspace, Officer] }\n",
            "",
        )
    )
    assert load_ruleset_document(disabled).ruleset.flagship.enabled is False


def test_dump_is_canonical_fixed_point():
    doc = load_ruleset_document(MINI_ATXXII)
    text = dump_document(doc)
    again = dump_document(load_ruleset_document(text))
    assert text == again
    assert (
        "ships:\n- {hull: Absolution, class: Command Ship}" in text
    )  # sorted, flow style, defaults pruned
    assert "flagship_eligible: false" in text and "flagship_eligible: null" not in text


def test_points_hash_ignores_metadata_and_order():
    doc = load_ruleset_document(MINI_ATXXII)
    relabelled = load_ruleset_document(MINI_ATXXII.replace("label: Test table", "label: Other"))
    reordered = load_ruleset_document(
        MINI_ATXXII.replace("  - { name: Frigate, size: FR, points: 3 }\n", "").replace(
            "ship_classes:\n", "ship_classes:\n  - { name: Frigate, size: FR, points: 3 }\n"
        )
    )
    changed = load_ruleset_document(MINI_ATXXII.replace("points: 33", "points: 34"))
    assert (
        yaml_io.points_hash(doc)
        == yaml_io.points_hash(relabelled)
        == yaml_io.points_hash(reordered)
    )
    assert yaml_io.points_hash(doc) != yaml_io.points_hash(changed)
