from django.core.management.base import BaseCommand

from apps.accounts.services import refresh_affiliations
from apps.esi.client import EsiError


class Command(BaseCommand):
    help = "Refresh corp/alliance for all known characters and re-apply admission rules."

    def handle(self, *args, **options):
        try:
            result = refresh_affiliations()
        except EsiError as exc:
            self.stderr.write(f"ESI unavailable, skipping this run: {exc}")
            return
        self.stdout.write(
            "characters updated: {characters_updated}, suspended: {suspended}, "
            "reactivated: {reactivated}".format(**result)
        )
