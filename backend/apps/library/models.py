from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

from apps.sde.models import EveType


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
