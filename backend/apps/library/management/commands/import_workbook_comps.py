"""Load the practice organizer's `Comp library` (+ `Comp Notes`) sheets into Comp/CompSlot."""

from dataclasses import dataclass, field
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.importing import ImportReport
from apps.library import comps, services
from apps.library.comps import SlotPatch
from apps.library.constants import LINK_SCRIPT_RE, LINK_SCRIPTS
from apps.library.models import CompStatus, Fit
from apps.rules.models import Ruleset
from apps.sde.models import EveType

FIRST_DATA_ROW = 6
# Column indexes (0-based) in `Comp library`: G flag, H slot, I status, J name, K ship, L warp-in,
# U..Y scripts, Z note, AA default fit
COL_FLAG, COL_SLOT, COL_STATUS, COL_NAME, COL_SHIP, COL_WARP = 6, 7, 8, 9, 10, 11
COL_SCRIPTS = range(20, 25)
COL_NOTE, COL_FIT = 25, 26
STATUS_MAP = {s.label.lower(): s.value for s in CompStatus}


@dataclass
class Block:
    name: str
    first_row: int
    status_raw: str | None = None
    rows: list[tuple[int, list]] = field(default_factory=list)


def _cell(row: list, idx: int):
    return row[idx] if idx < len(row) else None


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def read_blocks(ws) -> list[Block]:
    blocks: list[Block] = []
    current: Block | None = None
    for row_no, row in enumerate(
        ws.iter_rows(min_row=FIRST_DATA_ROW, values_only=True), start=FIRST_DATA_ROW
    ):
        cells = list(row)
        name = _text(_cell(cells, COL_NAME))
        if not name:
            current = None
            continue
        if current is None or current.name != name:
            current = Block(
                name=name, first_row=row_no, status_raw=_text(_cell(cells, COL_STATUS)) or None
            )
            blocks.append(current)
        elif current.status_raw is None and _text(_cell(cells, COL_STATUS)):
            current.status_raw = _text(_cell(cells, COL_STATUS))
        current.rows.append((row_no, cells))
    return blocks


def read_notes(ws, comp_names: set[str]) -> dict[str, tuple[str, str]]:
    """`Comp Notes`: C comp name, E notes, F ban theory; rows naming fits are skipped."""
    lowered = {n.lower(): n for n in comp_names}
    out: dict[str, tuple[str, str]] = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        cells = list(row)
        key = _text(_cell(cells, 2)).lower()
        if key in lowered:
            notes, ban_theory = _text(_cell(cells, 4)), _text(_cell(cells, 5))
            if notes or ban_theory:
                out[lowered[key]] = (notes, ban_theory)
    return out


class Command(BaseCommand):
    help = "Import comps from the practice organizer workbook (.xlsx)"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument(
            "--ruleset", default="ATXXII", help="tournament code the comps belong to"
        )
        parser.add_argument("--sheet", default="Comp library")
        parser.add_argument("--notes-sheet", default="Comp Notes")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="replace comps that already exist (default: keep them and their in-app edits)",
        )

    def handle(self, *args, **options):
        from openpyxl import load_workbook

        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"{path} does not exist")
        ruleset = (
            Ruleset.objects.select_related("tournament")
            .filter(tournament__code=options["ruleset"])
            .first()
        )
        if ruleset is None:
            raise CommandError(f"ruleset {options['ruleset']!r} is not imported")
        report = ImportReport(source=str(path))
        wb = load_workbook(path, read_only=True, data_only=True)
        if options["sheet"] not in wb.sheetnames:
            raise CommandError(f"sheet {options['sheet']!r} not found; have {wb.sheetnames}")
        blocks = read_blocks(wb[options["sheet"]])
        notes = (
            read_notes(wb[options["notes_sheet"]], {b.name for b in blocks})
            if options["notes_sheet"] in wb.sheetnames
            else {}
        )
        counts = report.file("comps")
        n = ruleset.fielded_pilots
        hull_cache: dict[str, EveType | None] = {}
        with transaction.atomic():
            for block in blocks:
                counts.seen += 1
                status = STATUS_MAP.get((block.status_raw or "").lower())
                if status is None:
                    report.warn(
                        f"row {block.first_row}: {block.name}: unknown status {block.status_raw!r}; construction"
                    )
                    status = CompStatus.CONSTRUCTION
                patches: dict[int, SlotPatch] = {}
                for row_no, cells in block.rows:
                    try:
                        slot_no = int(float(_cell(cells, COL_SLOT)))  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        report.warn(f"row {row_no}: {block.name}: no slot number; skipped")
                        continue
                    if not 1 <= slot_no <= n or slot_no in patches:
                        report.warn(
                            f"row {row_no}: {block.name}: slot {slot_no} out of range or repeated"
                        )
                        continue
                    ship_name = _text(_cell(cells, COL_SHIP))
                    ship: EveType | None = None
                    if ship_name:
                        if ship_name not in hull_cache:
                            hull_cache[ship_name] = services.resolve_hull(ship_name)
                        ship = hull_cache[ship_name]
                        if ship is None:
                            report.warn(f"row {row_no}: {block.name}: unknown hull {ship_name!r}")
                    fit_id = None
                    fit_name = _text(_cell(cells, COL_FIT))
                    if ship is not None and fit_name and fit_name.lower() != "none":
                        fit = Fit.objects.filter(ship=ship, name__iexact=fit_name).first()
                        if fit is None:
                            report.warn(
                                f"row {row_no}: {block.name}: no fit {fit_name!r} for {ship.name}"
                            )
                        else:
                            fit_id = fit.pk
                    codes: list[str] = []
                    for idx in COL_SCRIPTS:
                        raw = _text(_cell(cells, idx))
                        if not raw or raw.lower() == "none":
                            continue
                        m = LINK_SCRIPT_RE.match(raw)
                        code = m.group(1).upper() if m else None
                        if code not in LINK_SCRIPTS:
                            report.warn(f"row {row_no}: {block.name}: unknown link script {raw!r}")
                            continue
                        if code not in codes:
                            codes.append(code)
                    warp = _cell(cells, COL_WARP)
                    try:
                        warp_km = int(float(warp)) if warp not in (None, "") else None
                    except (TypeError, ValueError):
                        warp_km = None
                    if warp_km is not None and not 0 <= warp_km <= 1000:
                        report.warn(f"row {row_no}: {block.name}: warp-in {warp_km} km dropped")
                        warp_km = None
                    flag = _cell(cells, COL_FLAG)
                    patches[slot_no] = SlotPatch(
                        slot_no=slot_no,
                        type_id=ship.pk if ship is not None else None,
                        is_flagship=flag is True or _text(flag).lower() == "true",
                        warp_in_km=warp_km,
                        default_fit_id=fit_id,
                        ship_note=_text(_cell(cells, COL_NOTE)),
                        link_scripts=tuple(codes),
                    )
                for slot_no in range(1, n + 1):
                    patches.setdefault(slot_no, SlotPatch(slot_no=slot_no))
                note_text, ban_theory = notes.get(block.name, ("", ""))
                try:
                    _, outcome = comps.upsert_imported_comp(
                        ruleset=ruleset,
                        name=block.name,
                        status=status,
                        notes=note_text,
                        ban_theory=ban_theory,
                        slots=list(patches.values()),
                        overwrite=options["overwrite"],
                    )
                except comps.CompError as exc:
                    report.fail(f"row {block.first_row}: {block.name}: {exc}")
                    continue
                report.derived[outcome] = report.derived.get(outcome, 0) + 1
                if outcome != "skipped":
                    counts.upserted += 1
            if options["dry_run"]:
                transaction.set_rollback(True)
                report.warn("dry run: nothing written")
        report.finish()
        self.stdout.write(report.summary())
        if not report.ok:
            raise CommandError("import finished with errors")
