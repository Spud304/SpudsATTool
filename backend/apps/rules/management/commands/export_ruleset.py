from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.rules.exporter import export_ruleset
from apps.rules.models import Ruleset


class Command(BaseCommand):
    help = "Export a ruleset as canonical YAML."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("code", help="tournament code, e.g. ATXXII")
        parser.add_argument("--out", type=Path, help="write to this file instead of stdout")

    def handle(self, *args, **options) -> None:
        ruleset = (
            Ruleset.objects.filter(tournament__code=options["code"])
            .select_related("tournament")
            .first()
        )
        if ruleset is None:
            raise CommandError(f"no ruleset with code {options['code']!r}")
        text = export_ruleset(ruleset)
        if options["out"]:
            options["out"].write_text(text, encoding="utf-8")
            self.stdout.write(f"wrote {options['out']}")
        else:
            self.stdout.write(text)
