"""Scrim sessions: roster, attendance, sets, rounds, lineups, bans and the live-event log."""

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.library.models import Archetype, Comp, Fit
from apps.sde.models import EveType

if TYPE_CHECKING:
    from django_stubs_ext.db.models.manager import RelatedManager


class PilotStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class Pilot(models.Model):
    """A person on the roster. Linked to a login when they have one; mercs and alumni may never log in."""

    name = models.CharField(max_length=100)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pilot",
    )
    status = models.CharField(
        max_length=10, choices=PilotStatus.choices, default=PilotStatus.ACTIVE, db_index=True
    )
    is_merc = models.BooleanField(default=False)
    roles_text = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        user_id: int | None

    class Meta:
        db_table = "scrims_pilot"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="scrims_pilot_name_uniq")]

    def __str__(self) -> str:
        return self.name


class Opponent(models.Model):
    name = models.CharField(max_length=100, unique=True)
    notes = models.TextField(blank=True)
    alliance_id = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "scrims_opponent"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WarpInLabel(models.Model):
    label = models.CharField(max_length=40, unique=True)
    sort_order = models.SmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "scrims_warp_in_label"
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label


class LiveManager(models.Manager):
    """Default manager for soft-deleted rows: hides them everywhere, including reverse relations.

    `all_objects` on the same model reaches the deleted rows for restore and purge.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SessionKind(models.TextChoices):
    PRACTICE = "practice", "Practice"
    SCRIM = "scrim", "Scrim"
    TOURNAMENT_MATCH = "tournament_match", "Tournament match"
    WARMUP = "warmup", "Warm-up"


class Side(models.TextChoices):
    A = "A", "Team A"
    B = "B", "Team B"


class Session(models.Model):
    """One night against one opponent. Sets hang off it; `event_seq` orders the live-event stream."""

    ruleset = models.ForeignKey("rules.Ruleset", on_delete=models.PROTECT, related_name="sessions")
    stage = models.ForeignKey(
        "rules.Stage", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    point_table_version = models.ForeignKey(
        "rules.PointTableVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    kind = models.CharField(
        max_length=20, choices=SessionKind.choices, default=SessionKind.PRACTICE
    )
    title = models.CharField(max_length=120)
    date = models.DateTimeField()
    opponent = models.ForeignKey(
        Opponent, on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions"
    )
    system_name = models.CharField(max_length=60, blank=True)
    moveme_system = models.CharField(max_length=60, blank=True)
    motd = models.TextField(blank=True)
    default_our_side = models.CharField(max_length=1, choices=Side.choices, blank=True)
    is_archived = models.BooleanField(default=False)
    event_seq = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        ruleset_id: int
        stage_id: int | None
        point_table_version_id: int | None
        opponent_id: int | None
        created_by_id: int | None
        attendance: "RelatedManager[SessionAttendance]"
        sets: "RelatedManager[Set]"
        events: "RelatedManager[ChangeEvent]"

    class Meta:
        db_table = "scrims_session"
        ordering = ["-date"]

    def __str__(self) -> str:
        return self.title


class Rsvp(models.TextChoices):
    YES = "yes", "Attending"
    NO = "no", "Unable"
    MAYBE = "maybe", "Maybe"
    NONE = "none", "No answer"


class Attendance(models.TextChoices):
    PRESENT = "present", "Present"
    LATE = "late", "Late"
    ABSENT = "absent", "Absent"
    NO_SHOW = "no_show", "No-show"
    NONE = "none", "Not set"


class SessionAttendance(models.Model):
    """RSVP is the pilot's own signup before the night; attendance is what happened, set by a captain."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="attendance")
    pilot = models.ForeignKey(Pilot, on_delete=models.CASCADE, related_name="attendance")
    rsvp = models.CharField(max_length=6, choices=Rsvp.choices, default=Rsvp.NONE)
    rsvp_reason = models.CharField(max_length=200, blank=True)
    rsvp_at = models.DateTimeField(null=True, blank=True)
    attendance = models.CharField(max_length=8, choices=Attendance.choices, default=Attendance.NONE)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    removed_reason = models.CharField(max_length=200, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    if TYPE_CHECKING:
        session_id: int
        pilot_id: int

    class Meta:
        db_table = "scrims_session_attendance"
        constraints = [
            models.UniqueConstraint(fields=["session", "pilot"], name="scrims_attendance_uniq")
        ]


class Set(models.Model):
    """One ban phase plus the rounds fought under it."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="sets")
    index = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=60, blank=True)
    comp = models.ForeignKey(
        Comp, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    our_archetype = models.ForeignKey(
        Archetype, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    opp_archetype = models.ForeignKey(
        Archetype, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    our_side = models.CharField(max_length=1, choices=Side.choices, default=Side.A)
    tactics_note = models.TextField(blank=True)
    link_note = models.CharField(max_length=300, blank=True)
    warp_calls = models.JSONField(default=list, blank=True)  # four labels, 1st..4th
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    objects = LiveManager()
    all_objects = models.Manager()

    if TYPE_CHECKING:
        session_id: int
        comp_id: int | None
        our_archetype_id: int | None
        opp_archetype_id: int | None
        rounds: "RelatedManager[Round]"
        bans: "RelatedManager[Ban]"

    class Meta:
        db_table = "scrims_set"
        ordering = ["index"]
        constraints = [models.UniqueConstraint(fields=["session", "index"], name="scrims_set_uniq")]


class Outcome(models.TextChoices):
    WIN = "win", "Win"
    LOSS = "loss", "Loss"
    DRAW = "draw", "Draw"
    NONE = "none", "Not played"
    RESET = "reset", "Reset"


class Round(models.Model):
    set = models.ForeignKey(Set, on_delete=models.CASCADE, related_name="rounds")
    round_no = models.PositiveSmallIntegerField()
    outcome = models.CharField(max_length=5, choices=Outcome.choices, default=Outcome.NONE)
    notes = models.TextField(blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    objects = LiveManager()
    all_objects = models.Manager()

    if TYPE_CHECKING:
        set_id: int
        assignments: "RelatedManager[Assignment]"

    class Meta:
        db_table = "scrims_round"
        ordering = ["round_no"]
        constraints = [
            models.UniqueConstraint(fields=["set", "round_no"], name="scrims_round_uniq")
        ]


class LineupSide(models.TextChoices):
    US = "US", "Us"
    OPP = "OPP", "Opponent"


class Assignment(models.Model):
    """One slot on one side of one round. A new round copies the previous round's rows."""

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="assignments")
    side = models.CharField(max_length=3, choices=LineupSide.choices)
    slot_no = models.PositiveSmallIntegerField()
    pilot = models.ForeignKey(
        Pilot, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    opp_pilot_name = models.CharField(max_length=100, blank=True)
    ship = models.ForeignKey(
        EveType, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    is_flagship = models.BooleanField(default=False)
    is_unique = models.BooleanField(default=False)
    warp_in_km = models.SmallIntegerField(null=True, blank=True)
    fit = models.ForeignKey(Fit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    fit_text_snapshot = models.TextField(blank=True)
    load_default = models.BooleanField(default=True)
    custom_note = models.CharField(max_length=300, blank=True)
    repeat_note = models.CharField(
        max_length=300, blank=True
    )  # the comp's ship note, copied on load
    link_scripts = models.JSONField(default=list, blank=True)
    died = models.BooleanField(default=False)

    if TYPE_CHECKING:
        round_id: int
        pilot_id: int | None
        ship_id: int | None
        fit_id: int | None

    class Meta:
        db_table = "scrims_assignment"
        ordering = ["side", "slot_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["round", "side", "slot_no"], name="scrims_assignment_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(pilot__isnull=True) | models.Q(side="US"),
                name="scrims_assignment_pilot_us_only",
            ),
        ]


class BanKind(models.TextChoices):
    STANDARD = "standard", "Standard"
    AVALANCHE = "avalanche", "Avalanche"
    UNIQUE_EXTRA = "unique_extra", "Unique-hull extra"


class Ban(models.Model):
    set = models.ForeignKey(Set, on_delete=models.CASCADE, related_name="bans")
    side = models.CharField(max_length=1, choices=Side.choices)
    kind = models.CharField(max_length=12, choices=BanKind.choices, default=BanKind.STANDARD)
    index = models.PositiveSmallIntegerField()
    ship = models.ForeignKey(
        EveType, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    in_effect_from_round = models.PositiveSmallIntegerField(default=1)

    if TYPE_CHECKING:
        set_id: int
        ship_id: int | None

    class Meta:
        db_table = "scrims_ban"
        ordering = ["kind", "index", "side"]
        constraints = [
            models.UniqueConstraint(fields=["set", "side", "kind", "index"], name="scrims_ban_uniq")
        ]


class ChangeEvent(models.Model):
    """Append-only stream of session changes; the SSE replay buffer."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="events")
    seq = models.PositiveIntegerField()
    kind = models.CharField(max_length=32)
    payload = models.JSONField(default=dict)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        session_id: int

    class Meta:
        db_table = "scrims_change_event"
        ordering = ["seq"]
        constraints = [models.UniqueConstraint(fields=["session", "seq"], name="scrims_event_uniq")]


class ShareLink(models.Model):
    """A public, read-only view of one scrim for whoever holds the token; fit text stays hidden."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="share_links")
    token = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    if TYPE_CHECKING:
        session_id: int

    class Meta:
        db_table = "scrims_share_link"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"share {self.token[:8]} for {self.session}"
