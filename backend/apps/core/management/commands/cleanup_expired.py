from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Invite


class Command(BaseCommand):
    help = "Remove expired sessions and invites."

    def handle(self, *args, **options):
        call_command("clearsessions")
        deleted, _ = Invite.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(f"expired invites removed: {deleted}")
