from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.sde.models import EveType

if TYPE_CHECKING:
    from django_stubs_ext.db.models.manager import RelatedManager


class FitStatus(models.TextChoices):
    SUGGESTED = "suggested", "Suggested"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    RETIRED = "retired", "Retired"


class Fit(models.Model):
    """One EFT fit for one hull. Stats and derived flags are refreshed by services, never by clients."""

    ship = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="fits")
    name = models.CharField(max_length=120)
    status = models.CharField(
        max_length=10, choices=FitStatus.choices, default=FitStatus.SUGGESTED, db_index=True
    )
    eft_text = models.TextField()
    pyfa_summary = models.TextField(blank=True)

    dps = models.FloatField(null=True, blank=True)
    volley = models.FloatField(null=True, blank=True)
    ehp_k = models.FloatField(null=True, blank=True)
    speed_ms = models.FloatField(null=True, blank=True)
    sig_radius_m = models.FloatField(null=True, blank=True)
    cap_stable_pct = models.FloatField(null=True, blank=True)
    cap_lasts_s = models.IntegerField(null=True, blank=True)
    targeting_range_km = models.FloatField(null=True, blank=True)
    stats_parse_ok = models.BooleanField(default=False)

    has_links = models.BooleanField(default=False)
    unresolved_names = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fits_created",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fits_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        ship_id: int
        created_by_id: int | None
        reviewed_by_id: int | None

    class Meta:
        db_table = "library_fit"
        ordering = ["ship__name", "name"]
        constraints = [models.UniqueConstraint(fields=["ship", "name"], name="library_fit_uniq")]

    def __str__(self) -> str:
        return f"{self.ship.name}: {self.name}"


class Archetype(models.Model):
    name = models.CharField(max_length=60, unique=True)
    description = models.TextField(blank=True)
    is_retired = models.BooleanField(default=False)
    sort_order = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "library_archetype"
        ordering = ["is_retired", "sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class CompStatus(models.TextChoices):
    SUGGESTED = "suggested", "Suggested"
    CONSTRUCTION = "construction", "Construction"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    RETIRED = "retired", "Retired"


class Comp(models.Model):
    """A team composition for one ruleset; slots 1..fielded_pilots are created with it."""

    ruleset = models.ForeignKey("rules.Ruleset", on_delete=models.PROTECT, related_name="comps")
    name = models.CharField(max_length=120)
    status = models.CharField(
        max_length=12, choices=CompStatus.choices, default=CompStatus.SUGGESTED, db_index=True
    )
    archetype = models.ForeignKey(
        Archetype, on_delete=models.SET_NULL, null=True, blank=True, related_name="comps"
    )
    notes = models.TextField(blank=True)
    ban_theory = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comps_created",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comps_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        ruleset_id: int
        archetype_id: int | None
        created_by_id: int | None
        reviewed_by_id: int | None
        slots: "RelatedManager[CompSlot]"

    class Meta:
        db_table = "library_comp"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), "ruleset", name="library_comp_uniq")]

    def __str__(self) -> str:
        return self.name


class CompSlot(models.Model):
    comp = models.ForeignKey(Comp, on_delete=models.CASCADE, related_name="slots")
    slot_no = models.PositiveSmallIntegerField()
    ship = models.ForeignKey(
        EveType, on_delete=models.PROTECT, null=True, blank=True, related_name="comp_slots"
    )
    is_flagship = models.BooleanField(default=False)
    is_unique = models.BooleanField(default=False)
    warp_in_km = models.SmallIntegerField(null=True, blank=True)
    default_fit = models.ForeignKey(
        Fit, on_delete=models.SET_NULL, null=True, blank=True, related_name="comp_slots"
    )
    ship_note = models.CharField(max_length=300, blank=True)
    link_scripts = models.JSONField(default=list, blank=True)  # up to 5 codes from LINK_SCRIPTS

    if TYPE_CHECKING:
        comp_id: int
        ship_id: int | None
        default_fit_id: int | None

    class Meta:
        db_table = "library_comp_slot"
        ordering = ["slot_no"]
        constraints = [
            models.UniqueConstraint(fields=["comp", "slot_no"], name="library_comp_slot_uniq")
        ]

    def __str__(self) -> str:
        return f"{self.comp_id}#{self.slot_no}"


class Scratchpad(models.Model):
    """One member's comp scratchpad, saved so leaving the page loses nothing. Private, not audited."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scratchpad"
    )
    ruleset = models.ForeignKey(
        "rules.Ruleset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    slots = models.JSONField(default=list)  # [{type_id, is_flagship, has_links}, ...]
    bans = models.JSONField(default=list)  # [type_id, ...]
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "library_scratchpad"
