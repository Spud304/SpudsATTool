import secrets
from typing import TYPE_CHECKING, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from django_stubs_ext.db.models.manager import RelatedManager


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    CAPTAIN = "captain", "Captain"
    THEORYCRAFTER = "theorycrafter", "Theorycrafter"
    PILOT = "pilot", "Pilot"
    GUEST = "guest", "Guest"
    VIEWER = "viewer", "Viewer"


# Higher rank implies every capability of the lower ranks. Guest is a restricted read role
# handled explicitly in permissions.py.
ROLE_RANK = {
    Role.VIEWER: 0,
    Role.GUEST: 0,
    Role.PILOT: 1,
    Role.THEORYCRAFTER: 2,
    Role.CAPTAIN: 3,
    Role.ADMIN: 4,
}


class UserManager(BaseUserManager):
    def create_user(self, username: str, **extra) -> "User":
        user = self.model(username=username, **extra)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, username: str, email: str | None = None, password: str | None = None, **extra
    ) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("display_name", username)
        user = self.model(username=username, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """A person. Logs in only through EVE SSO and owns one or more characters."""

    username = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=100)
    main_character = models.ForeignKey(
        "accounts.EveCharacter", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = UserManager()

    if TYPE_CHECKING:
        characters: "RelatedManager[EveCharacter]"
        membership: "Membership"
        main_character_id: int | None

    class Meta:
        db_table = "accounts_user"

    def __str__(self) -> str:
        return self.display_name or self.username


class EveCharacter(models.Model):
    character_id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    owner_hash = models.CharField(max_length=64, blank=True)
    corporation_id = models.BigIntegerField(null=True, blank=True)
    corporation_name = models.CharField(max_length=100, blank=True)
    alliance_id = models.BigIntegerField(null=True, blank=True)
    alliance_name = models.CharField(max_length=100, blank=True)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="characters"
    )
    affiliation_checked_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        user_id: int | None

    class Meta:
        db_table = "accounts_eve_character"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class MembershipStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    REMOVED = "removed", "Removed"


class MembershipSource(models.TextChoices):
    ENV_ADMIN = "env_admin", "ADMIN_CHARACTER_IDS"
    EXPLICIT = "explicit", "Set by an admin"
    INVITE = "invite", "Invite link"
    RULE = "rule", "Admission rule"


class Membership(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="membership")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PILOT)
    status = models.CharField(
        max_length=20, choices=MembershipStatus.choices, default=MembershipStatus.ACTIVE
    )
    source = models.CharField(
        max_length=20, choices=MembershipSource.choices, default=MembershipSource.EXPLICIT
    )
    is_leadership = models.BooleanField(
        default=False, help_text="Grants access to pilot notes and the audit log."
    )
    suspended_at = models.DateTimeField(null=True, blank=True)
    # A rule-sourced member who stops matching any rule is suspended only after the team's
    # grace period, so a corp shuffle does not lock people out mid-week.
    rule_failed_since = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_membership"

    def __str__(self) -> str:
        return f"{self.user} ({self.role}, {self.status})"


class AdmissionRuleKind(models.TextChoices):
    CORPORATION = "corporation", "Corporation"
    ALLIANCE = "alliance", "Alliance"


class AdmissionRule(models.Model):
    kind = models.CharField(max_length=20, choices=AdmissionRuleKind.choices)
    entity_id = models.BigIntegerField()
    entity_name = models.CharField(max_length=100, blank=True)
    default_role = models.CharField(max_length=20, choices=Role.choices, default=Role.PILOT)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_admission_rule"
        constraints = [
            models.UniqueConstraint(fields=["kind", "entity_id"], name="accounts_rule_entity_uniq")
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.entity_name or self.entity_id} -> {self.default_role}"

    def matches(self, character: EveCharacter) -> bool:
        if not self.enabled:
            return False
        if self.kind == AdmissionRuleKind.CORPORATION:
            return character.corporation_id == self.entity_id
        return character.alliance_id == self.entity_id


def _new_invite_token() -> str:
    return secrets.token_urlsafe(24)


class Invite(models.Model):
    token = models.CharField(max_length=64, unique=True, default=_new_invite_token)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PILOT)
    uses_left = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField()
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_invite"

    def __str__(self) -> str:
        return f"invite {self.token[:6]}... ({self.role})"

    @property
    def is_valid(self) -> bool:
        return self.uses_left > 0 and self.expires_at > timezone.now()
