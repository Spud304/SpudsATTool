from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import Membership, MembershipStatus
from apps.core.models import Team


class Command(BaseCommand):
    help = "First-run setup: create the Team row and report anything still unconfigured."

    def handle(self, *args, **options):
        team = Team.get_solo()
        self.stdout.write(f"team: {team.name} (slug {team.slug})")
        if not settings.EVE_CLIENT_ID or not settings.EVE_CLIENT_SECRET:
            self.stderr.write("EVE_CLIENT_ID / EVE_CLIENT_SECRET are not set: EVE login will fail.")
        if not settings.ADMIN_CHARACTER_IDS:
            self.stderr.write(
                "ADMIN_CHARACTER_IDS is empty: no admin can be admitted. Add your character id."
            )
        else:
            self.stdout.write(f"admin characters: {settings.ADMIN_CHARACTER_IDS}")
        admins = Membership.objects.filter(
            role__is_system=True, status=MembershipStatus.ACTIVE
        ).count()
        self.stdout.write(f"active admins who have logged in: {admins}")
