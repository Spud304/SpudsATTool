import logging
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.core.importing import ImportFailed
from apps.core.locks import advisory_lock
from apps.sde import download, incoming
from apps.sde.constants import SDE_IMPORT_LOCK_KEY
from apps.sde.jsonl import detect_build, open_source
from apps.sde.loader import import_source
from apps.sde.models import SdeBuild

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import CCP's JSONL SDE from a zip/folder, the incoming drop folder, or CCP's download."

    def add_arguments(self, parser: CommandParser) -> None:
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--path", type=Path, help="SDE zip or a folder of .jsonl files")
        mode.add_argument(
            "--scan-incoming",
            action="store_true",
            help="import settled zips from instance/sde/incoming",
        )
        mode.add_argument(
            "--check-latest",
            action="store_true",
            help="download and import CCP's latest build if newer",
        )
        parser.add_argument("--build", type=int, help="override the build number for --path")
        parser.add_argument("--files", help="comma-separated subset of SDE files to load")
        parser.add_argument(
            "--download-only",
            action="store_true",
            help="with --check-latest: fetch but do not import",
        )
        parser.add_argument("--raw-only", action="store_true", help="skip typed derivation")
        parser.add_argument("--force", action="store_true", help="allow importing an older build")
        parser.add_argument(
            "--dry-run", action="store_true", help="stream and count without writing"
        )

    def handle(self, *args, **options) -> None:
        files = (
            [f.strip() for f in options["files"].split(",") if f.strip()]
            if options["files"]
            else None
        )
        with advisory_lock(SDE_IMPORT_LOCK_KEY) as acquired:
            if not acquired:
                self.stdout.write("another SDE import is running; skipping")
                return
            try:
                if options["path"]:
                    self._from_path(options, files)
                elif options["scan_incoming"]:
                    self._scan_incoming(options, files)
                else:
                    self._check_latest(options, files)
            except ImportFailed as exc:
                self.stderr.write(str(exc))
                raise CommandError(exc.remediation or "import failed") from exc
        if not options["dry_run"] and not options["download_only"]:
            # Shipped rulesets need ship names from the SDE, so they load once it is in.
            call_command("load_rulesets", stdout=self.stdout, stderr=self.stderr)

    def _from_path(self, options: dict, files: list[str] | None) -> None:
        with open_source(options["path"]) as source:
            build, release_date = detect_build(
                source, path=options["path"], override=options["build"]
            )
            report = import_source(
                source,
                build=build,
                release_date=release_date,
                files=files,
                force=options["force"],
                dry_run=options["dry_run"],
                raw_only=options["raw_only"],
            )
        self.stdout.write(report.summary())

    def _scan_incoming(self, options: dict, files: list[str] | None) -> None:
        reports = incoming.scan_incoming(force=options["force"], files=files)
        if not reports:
            self.stdout.write("incoming: nothing to import")
        for report in reports:
            self.stdout.write(report.summary())
        if any(not r.ok for r in reports):
            raise CommandError("one or more incoming archives failed; see instance/sde/failed/")

    def _check_latest(self, options: dict, files: list[str] | None) -> None:
        if not settings.SDE_AUTO_DOWNLOAD and not options["force"]:
            self.stdout.write("SDE_AUTO_DOWNLOAD is off; pass --force to download anyway")
            return
        latest = download.fetch_latest_build()
        current = SdeBuild.latest()
        if current is not None:
            current.last_checked_at = timezone.now()
            current.save(update_fields=["last_checked_at"])
            if latest.build <= current.build and not options["force"]:
                self.stdout.write(
                    f"already imported build {current.build} (CCP latest is {latest.build})"
                )
                return
        dirs = incoming.sde_dirs()
        path = download.download_build(latest.build, dirs["downloads"])
        if options["download_only"]:
            self.stdout.write(f"downloaded {path}")
            return
        with open_source(path) as source:
            build, release_date = detect_build(source, path=path)
            report = import_source(
                source,
                build=build,
                release_date=release_date or latest.release_date,
                files=files,
                force=options["force"],
                dry_run=options["dry_run"],
                raw_only=options["raw_only"],
            )
        download.prune_downloads(dirs["downloads"])
        self.stdout.write(report.summary())
