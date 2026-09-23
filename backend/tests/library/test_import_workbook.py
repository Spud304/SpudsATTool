import pytest
from django.core.management import CommandError, call_command
from openpyxl import Workbook

from apps.library.models import Fit
from tests.conftest import ABSO_FIT, ABSO_PYFA

pytestmark = pytest.mark.django_db

HEADER = ["filter", "lookup", "Validate", "Status", "Ship", "Fit name", "Fit", "Pyfa summary"]


def make_workbook(path, rows):
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fit library"
    ws.append(["instructions"])
    ws.append([])
    ws.append(HEADER)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def test_import_rows(tmp_path, library_sde, capsys):
    path = make_workbook(
        tmp_path / "fits.xlsx",
        [
            ["", "", "Valid", "Active", "Absolution", "Octo Ewar Abso", ABSO_FIT, ABSO_PYFA],
            ["", "", "Valid", "Retired", "Absolution", "No text", None, None],
            ["", "", "Valid", "Inactive", "Rifter", "Wrong header", ABSO_FIT, None],
            ["", "", "Valid", "Weird", "Rifter", "Bad status", ABSO_FIT, None],
            [None, None, None, None, None, None, None, None],
            ["", "", "Valid", "Active", "Rifter", "After blank", ABSO_FIT, None],
        ],
    )
    call_command("import_workbook_fits", str(path))
    out = capsys.readouterr().out
    assert Fit.objects.count() == 2
    abso = Fit.objects.get(name="Octo Ewar Abso")
    assert (
        abso.status == "active" and abso.dps == 709 and abso.has_links and abso.created_by is None
    )
    assert Fit.objects.get(name="Wrong header").ship.name == "Rifter"
    assert (
        "no EFT text" in out and "EFT header says 'Absolution'" in out and "unknown status" in out
    )
    assert "After blank" not in out

    call_command("import_workbook_fits", str(path))
    assert Fit.objects.count() == 2


def test_dry_run_and_unknown_hull(tmp_path, library_sde):
    path = make_workbook(
        tmp_path / "fits.xlsx",
        [["", "", "Valid", "Active", "Absolution", "Octo", ABSO_FIT, None]],
    )
    call_command("import_workbook_fits", str(path), "--dry-run")
    assert Fit.objects.count() == 0
    bad = make_workbook(
        tmp_path / "bad.xlsx", [["", "", "Valid", "Active", "Nope Hull", "x", ABSO_FIT, None]]
    )
    with pytest.raises(CommandError):
        call_command("import_workbook_fits", str(bad))


def test_reimport_keeps_in_app_edits_unless_overwrite(tmp_path, library_sde, capsys):
    from apps.audit.models import AuditLog

    path = make_workbook(
        tmp_path / "fits.xlsx",
        [["", "", "Valid", "Active", "Absolution", "Octo Ewar Abso", ABSO_FIT, ABSO_PYFA]],
    )
    call_command("import_workbook_fits", str(path))
    Fit.objects.filter(name="Octo Ewar Abso").update(status="retired")  # changed in the app
    call_command("import_workbook_fits", str(path))
    assert Fit.objects.get(name="Octo Ewar Abso").status == "retired"
    assert "skipped: 1" in capsys.readouterr().out
    call_command("import_workbook_fits", str(path), "--overwrite")
    assert Fit.objects.get(name="Octo Ewar Abso").status == "active"
    entry = AuditLog.objects.get(action="fit.overwritten_by_import")
    assert entry.before["status"] == "retired" and entry.before["eft_text"].startswith(
        "[Absolution"
    )
