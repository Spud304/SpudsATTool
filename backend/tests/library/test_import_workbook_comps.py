import pytest
from django.core.management import CommandError, call_command
from openpyxl import Workbook

from apps.audit.models import AuditLog
from apps.library import services
from apps.library.models import Comp
from apps.sde.models import EveType
from tests.conftest import ABSO_FIT

pytestmark = pytest.mark.django_db

HULLS = [
    "Astarte",
    "Astarte",
    "Absolution",
    "Zealot",
    "Ashimmu",
    "Augoror Navy Issue",
    "Keres",
    "Deacon",
    "Deacon",
    "Maulus",
]


def comp_row(slot, name, ship, status=None, flag=False, warp=None, scripts=(), note="", fit=""):
    row = [None] * 27
    row[6], row[7], row[8], row[9], row[10], row[11] = flag, float(slot), status, name, ship, warp
    for i, s in enumerate(scripts):
        row[20 + i] = s
    row[25], row[26] = note, fit
    return row


def make_workbook(path, comp_rows, note_rows):
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Comp library"
    for _ in range(5):
        ws.append(["header"])
    for row in comp_rows:
        ws.append(row)
    notes = wb.create_sheet("Comp Notes")
    for _ in range(3):
        notes.append(["header"])
    for row in note_rows:
        notes.append(row)
    wb.save(path)
    return path


def test_import_blocks(tmp_path, library_sde, imported_atxxii, capsys):
    absolution = EveType.objects.get(name="Absolution")
    services.upsert_imported_fit(
        ship=absolution, name="Octo Ewar Abso", status="active", eft_text=ABSO_FIT, pyfa_summary=""
    )
    rows = [
        comp_row(
            1,
            "Neon",
            HULLS[0],
            status="Active",
            warp=40.0,
            scripts=["(AE) Energizing", "(XX) Bogus"],
        ),
        comp_row(2, "Neon", HULLS[1], warp=40.0),
        comp_row(3, "Neon", HULLS[2], fit="Octo Ewar Abso", note="stay close"),
        comp_row(4, "Neon", HULLS[3], fit="Missing Fit"),
        *[comp_row(i, "Neon", HULLS[i - 1]) for i in range(5, 11)],
        [None] * 27,
        comp_row(1, "Odd", "Nope Hull", status="Weird", flag=True),
        comp_row(2, "Odd", "Rifter"),
        comp_row(11, "Odd", "Rifter"),
    ]
    notes = [
        [None, None, "Neon", "Active", "run it", "ban curse"],
        [None, None, "Octo Ewar Abso", None, "fit row to ignore", None],
    ]
    path = make_workbook(tmp_path / "comps.xlsx", rows, notes)
    call_command("import_workbook_comps", str(path))
    out = capsys.readouterr().out

    assert Comp.objects.count() == 2
    neon = Comp.objects.get(name="Neon")
    assert neon.status == "active" and neon.notes == "run it" and neon.ban_theory == "ban curse"
    slots = {s.slot_no: s for s in neon.slots.all()}
    assert slots[1].warp_in_km == 40 and slots[1].link_scripts == ["AE"]
    assert slots[3].default_fit is not None and slots[3].ship_note == "stay close"
    assert slots[4].default_fit is None
    odd = Comp.objects.get(name="Odd")
    assert odd.status == "construction" and odd.slots.get(slot_no=1).ship is None
    assert odd.slots.get(slot_no=1).is_flagship and odd.slots.get(slot_no=2).ship.name == "Rifter"
    assert "unknown link script '(XX) Bogus'" in out
    assert "no fit 'Missing Fit'" in out
    assert "unknown hull 'Nope Hull'" in out and "unknown status 'Weird'" in out
    assert "slot 11 out of range" in out

    Comp.objects.filter(name="Neon").update(notes="edited in the app")
    call_command("import_workbook_comps", str(path))
    assert Comp.objects.count() == 2
    assert Comp.objects.get(name="Neon").notes == "edited in the app"
    call_command("import_workbook_comps", str(path), "--overwrite")
    assert Comp.objects.get(name="Neon").notes == "run it"
    entry = AuditLog.objects.get(action="comp.overwritten_by_import", target_id=str(neon.pk))
    assert entry.before["notes"] == "edited in the app" and len(entry.before["slots"]) == 10


def test_dry_run_and_unknown_ruleset(tmp_path, library_sde, imported_atxxii):
    path = make_workbook(
        tmp_path / "c.xlsx",
        [comp_row(i, "Solo", HULLS[i - 1], status="Retired") for i in range(1, 11)],
        [],
    )
    call_command("import_workbook_comps", str(path), "--dry-run")
    assert Comp.objects.count() == 0
    with pytest.raises(CommandError):
        call_command("import_workbook_comps", str(path), "--ruleset", "NOPE")
