from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.importing import ImportFailed, ImportReport
from apps.core.locks import advisory_lock
from apps.rules.constants import RULES_IMPORT_LOCK_KEY
from apps.rules.importer import import_ruleset
from apps.rules.yaml_io import load_ruleset_document


class Command(BaseCommand):
    help = "Import a ruleset YAML document (see docs/rulesets.md)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--path", type=Path, required=True, help="ruleset .yaml file")
        parser.add_argument(
            "--dry-run", action="store_true", help="validate and resolve, then roll back"
        )
        parser.add_argument(
            "--replace-points",
            action="store_true",
            help="rewrite the current point table in place instead of creating a new version",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="allow an unverified document to replace a verified ruleset",
        )

    def handle(self, *args, **options) -> None:
        path: Path = options["path"]
        if not path.is_file():
            raise CommandError(f"{path} does not exist")
        report = ImportReport(source=str(path))
        try:
            doc = load_ruleset_document(path.read_text(encoding="utf-8"))
            with advisory_lock(RULES_IMPORT_LOCK_KEY) as acquired:
                if not acquired:
                    self.stdout.write("another rules import is running; skipping")
                    return
                import_ruleset(
                    doc,
                    report=report,
                    replace_points=options["replace_points"],
                    dry_run=options["dry_run"],
                    force=options["force"],
                )
        except ImportFailed as exc:
            self.stderr.write(str(exc))
            raise CommandError(exc.remediation or "import failed") from exc
        self.stdout.write(report.summary())
