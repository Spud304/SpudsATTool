from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.core.importing import ImportFailed, ImportReport
from apps.core.locks import advisory_lock
from apps.rules.constants import RULES_IMPORT_LOCK_KEY
from apps.rules.importer import import_ruleset
from apps.rules.models import Tournament
from apps.rules.yaml_io import load_ruleset_document
from apps.sde.models import EveType

FIXTURES_DIR = settings.BASE_DIR / "fixtures" / "rulesets"


class Command(BaseCommand):
    help = "Import the shipped ruleset documents whose tournament is not in the database yet."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dir", type=Path, default=FIXTURES_DIR, help="folder of .yaml files")

    def handle(self, *args, **options) -> None:
        if not EveType.objects.exists():
            self.stdout.write("rulesets: SDE not loaded yet; shipped rulesets will load after it")
            return
        paths = sorted(Path(options["dir"]).glob("*.yaml"))
        with advisory_lock(RULES_IMPORT_LOCK_KEY) as acquired:
            if not acquired:
                self.stdout.write("another rules import is running; skipping")
                return
            for path in paths:
                doc = load_ruleset_document(path.read_text(encoding="utf-8"))
                code = doc.tournament.code
                if Tournament.objects.filter(code=code).exists():
                    self.stdout.write(f"rulesets: {code} already present, left untouched")
                    continue
                report = ImportReport(source=str(path))
                try:
                    import_ruleset(doc, report=report)
                except ImportFailed as exc:
                    self.stderr.write(f"rulesets: {path.name} failed: {exc}")
                    continue
                self.stdout.write(f"rulesets: imported {code} from {path.name}")
