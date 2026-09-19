from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Team(models.Model):
    """The single team this deployment serves. Every library and scrim row will point here."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    alliance_id = models.BigIntegerField(null=True, blank=True)
    affiliation_grace_hours = models.PositiveIntegerField(default=24)
    # The season the team is working in; comps, fit legality and the comps list default to it.
    active_ruleset = models.ForeignKey(
        "rules.Ruleset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        active_ruleset_id: int | None

    class Meta:
        db_table = "core_team"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_solo(cls) -> "Team":
        team = cls.objects.order_by("id").first()
        if team is None:
            name = settings.TEAM_NAME
            team = cls.objects.create(name=name, slug=slugify(name) or "team")
        return team
