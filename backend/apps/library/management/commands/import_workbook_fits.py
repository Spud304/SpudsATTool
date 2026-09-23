"""Load the practice organizer's `Fit library` sheet: columns D status, E ship, F name, G EFT, H Pyfa."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.importing import ImportReport
from apps.library import services
from apps.library.eft import parse_eft
from apps.library.models import FitStatus

STATUS_MAP = {s.label.lower(): s.value for s in FitStatus}
FIRST_DATA_ROW = 4


class Command(BaseCommand):
    help = "Import fits from the practice organizer workbook (.xlsx)"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--sheet", default="Fit library")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="replace fits that already exist (default: keep them and their in-app edits)",
        )

    def handle(self, *args, **options):
        from openpyxl import load_workbook

        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"{path} does not exist")
        report = ImportReport(source=str(path))
        wb = load_workbook(path, read_only=True, data_only=True)
        if options["sheet"] not in wb.sheetnames:
            raise CommandError(f"sheet {options['sheet']!r} not found; have {wb.sheetnames}")
        ws = wb[options["sheet"]]
        counts = report.file("fits")
        with transaction.atomic():
            for row_no, row in enumerate(
                ws.iter_rows(min_row=FIRST_DATA_ROW, values_only=True), start=FIRST_DATA_ROW
            ):
                cells = list(row) + [None] * 8
                status_raw, ship_name, name, eft, pyfa = cells[3:8]
                if not ship_name:
                    break
                counts.seen += 1
                ship_name, name = str(ship_name).strip(), str(name or "").strip()
                status = STATUS_MAP.get(str(status_raw or "").strip().lower())
                if status is None:
                    report.warn(f"row {row_no}: unknown status {status_raw!r}; skipped")
                    continue
                if not name:
                    report.warn(f"row {row_no}: {ship_name} fit without a name; skipped")
                    continue
                if not eft or not str(eft).strip():
                    report.warn(f"row {row_no}: {ship_name} / {name}: no EFT text; skipped")
                    continue
                eft = str(eft).replace("\r\n", "\n")
                ship = services.resolve_hull(ship_name)
                if ship is None:
                    report.fail(f"row {row_no}: unknown hull {ship_name!r}")
                    continue
                header_hull = parse_eft(eft).hull_name
                if header_hull and header_hull.lower() != ship.name.lower():
                    report.warn(
                        f"row {row_no}: {ship.name} / {name}: EFT header says {header_hull!r}"
                    )
                fit, outcome, resolved = services.upsert_imported_fit(
                    ship=ship,
                    name=name,
                    status=status,
                    eft_text=eft,
                    pyfa_summary=str(pyfa or ""),
                    overwrite=options["overwrite"],
                )
                report.derived[outcome] = report.derived.get(outcome, 0) + 1
                if outcome == "skipped":
                    continue
                counts.upserted += 1
                for missing in resolved.unresolved:
                    report.warn(f"row {row_no}: {ship.name} / {name}: unknown item {missing!r}")
            if options["dry_run"]:
                transaction.set_rollback(True)
                report.warn("dry run: nothing written")
        report.finish()
        self.stdout.write(report.summary())
        if not report.ok:
            raise CommandError("import finished with errors")
