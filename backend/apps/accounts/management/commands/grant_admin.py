from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import EveCharacter, MembershipSource
from apps.accounts.services import grant_admin


class Command(BaseCommand):
    help = (
        "Grant admin to a character by id or exact name (recovery path for a locked-out install)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "character", help="character id, or exact name if it has logged in before"
        )

    def handle(self, *args, **options) -> None:
        ref: str = options["character"]
        if ref.isdigit():
            character, created = EveCharacter.objects.get_or_create(
                character_id=int(ref), defaults={"name": f"Character {ref}"}
            )
            if created:
                self.stdout.write(
                    "character has not logged in yet; it is admin now and its name fills in on first login"
                )
        else:
            character = EveCharacter.objects.filter(name=ref).first()
            if character is None:
                raise CommandError(f"no character named {ref!r} has logged in; use the id instead")
        membership = grant_admin(character, source=MembershipSource.EXPLICIT)
        self.stdout.write(f"{character.name} ({character.character_id}) is now {membership.role}")
