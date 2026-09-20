"""Remove rows the Playwright suite creates: `pw_`-prefixed names and the reserved character ids."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import AdmissionRule, EveCharacter, Invite, Membership, TeamRole, User
from apps.audit.models import AuditLog
from apps.library.models import Archetype, Comp, Fit
from apps.scrims.models import Opponent, Pilot, Session, WarpInLabel

PREFIX = "pw_"
CHARACTER_RANGE = (900_000_001, 900_000_099)
ENTITY_RANGE = (900_000_000, 900_999_999)


class Command(BaseCommand):
    help = "Delete Playwright test data (dev only)"

    def handle(self, *args, **options):
        if not settings.DEV_LOGIN_ENABLED:
            raise CommandError("refusing: DEV_LOGIN_ENABLED is off, this is not a dev database")
        lo, hi = CHARACTER_RANGE
        users = User.objects.filter(
            Q(username__in=[f"char:{i}" for i in range(lo, hi + 1)])
            | Q(characters__character_id__range=(lo, hi))
        ).distinct()
        user_ids = list(users.values_list("pk", flat=True))
        counts: dict[str, int] = {}
        with transaction.atomic():
            counts["scrims"] = Session.objects.filter(title__startswith=PREFIX).delete()[0]
            counts["opponents"] = Opponent.objects.filter(name__startswith=PREFIX).delete()[0]
            # Roster rows: hand-added pw_ pilots plus the ones the test logins create ("PW pilot").
            counts["pilots"] = Pilot.objects.filter(
                Q(name__startswith=PREFIX) | Q(name__startswith="PW ") | Q(user_id__in=user_ids)
            ).delete()[0]
            counts["comps"] = Comp.objects.filter(name__startswith=PREFIX).delete()[0]
            counts["fits"] = Fit.objects.filter(name__startswith=PREFIX).delete()[0]
            counts["archetypes"] = Archetype.objects.filter(name__startswith=PREFIX).delete()[0]
            counts["warp_labels"] = WarpInLabel.objects.filter(label__startswith=PREFIX).delete()[0]
            counts["invites"] = Invite.objects.filter(note__startswith=PREFIX).delete()[0]
            counts["admission_rules"] = AdmissionRule.objects.filter(
                entity_id__range=ENTITY_RANGE
            ).delete()[0]
            counts["audit"] = AuditLog.objects.filter(
                Q(target_label__startswith=PREFIX) | Q(actor_id__in=user_ids)
            ).delete()[0]
            counts["memberships"] = Membership.objects.filter(user_id__in=user_ids).delete()[0]
            counts["characters"] = EveCharacter.objects.filter(
                Q(character_id__range=(lo, hi)) | Q(user_id__in=user_ids)
            ).delete()[0]
            counts["users"] = User.objects.filter(pk__in=user_ids).delete()[0]
            pilot_role = TeamRole.objects.filter(slug="pilot").first()
            pw_roles = TeamRole.objects.filter(name__startswith=PREFIX, is_system=False)
            if pilot_role is not None:
                Membership.objects.filter(role__in=pw_roles).update(role=pilot_role)
                Invite.objects.filter(role__in=pw_roles).update(role=pilot_role)
                AdmissionRule.objects.filter(default_role__in=pw_roles).update(
                    default_role=pilot_role
                )
            counts["roles"] = pw_roles.delete()[0]
        self.stdout.write("playwright cleanup: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
