"""SDE mirror. Written only by the importer; never deleted, only flagged removed."""

from typing import TYPE_CHECKING

from django.db import models


class SdeRawRecord(models.Model):
    """One decoded SDE record from any included file."""

    file = models.CharField(max_length=64)
    key = models.CharField(max_length=64)
    data = models.JSONField()
    build = models.PositiveIntegerField()
    removed = models.BooleanField(default=False)

    class Meta:
        db_table = "sde_raw_record"
        constraints = [
            models.UniqueConstraint(fields=["file", "key"], name="sde_raw_record_file_key_uniq")
        ]
        indexes = [models.Index(fields=["file", "build"], name="sde_raw_record_file_build_idx")]

    def __str__(self) -> str:
        return f"{self.file}:{self.key}"


class SdeBuild(models.Model):
    """One row per imported SDE build; the newest is the live build."""

    build = models.PositiveIntegerField(unique=True)
    release_date = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField()
    last_checked_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=300, blank=True)
    files = models.JSONField(default=list, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    duration_s = models.FloatField(default=0.0)

    class Meta:
        db_table = "sde_build"
        ordering = ["-build"]

    def __str__(self) -> str:
        return f"SDE build {self.build}"

    @classmethod
    def latest(cls) -> "SdeBuild | None":
        return cls.objects.order_by("-build").first()


class EveCategory(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    published = models.BooleanField(default=False)
    removed = models.BooleanField(default=False)

    class Meta:
        db_table = "sde_eve_category"
        verbose_name_plural = "eve categories"

    def __str__(self) -> str:
        return self.name


class EveGroup(models.Model):
    id = models.IntegerField(primary_key=True)
    category = models.ForeignKey(EveCategory, on_delete=models.PROTECT, related_name="groups")
    name = models.CharField(max_length=100)
    published = models.BooleanField(default=False)
    removed = models.BooleanField(default=False)
    anchorable = models.BooleanField(default=False)
    anchored = models.BooleanField(default=False)
    fittable_non_singleton = models.BooleanField(default=False)
    use_base_price = models.BooleanField(default=False)

    if TYPE_CHECKING:
        category_id: int

    class Meta:
        db_table = "sde_eve_group"

    def __str__(self) -> str:
        return self.name


class EveMetaGroup(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    icon_id = models.IntegerField(null=True, blank=True)
    icon_suffix = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "sde_eve_meta_group"

    def __str__(self) -> str:
        return self.name


class EveFaction(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    corporation_id = models.IntegerField(null=True, blank=True)
    solar_system_id = models.IntegerField(null=True, blank=True)
    member_races = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "sde_eve_faction"

    def __str__(self) -> str:
        return self.name


class EveRace(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "sde_eve_race"

    def __str__(self) -> str:
        return self.name


class EveType(models.Model):
    """A hull, module, charge, drone, implant, deployable or subsystem."""

    id = models.IntegerField(primary_key=True)
    group = models.ForeignKey(EveGroup, on_delete=models.PROTECT, related_name="types")
    name = models.CharField(max_length=200)
    published = models.BooleanField(default=False)
    removed = models.BooleanField(default=False)
    faction = models.ForeignKey(
        EveFaction, null=True, blank=True, on_delete=models.PROTECT, related_name="types"
    )
    meta_group = models.ForeignKey(
        EveMetaGroup, null=True, blank=True, on_delete=models.PROTECT, related_name="types"
    )
    race = models.ForeignKey(
        EveRace, null=True, blank=True, on_delete=models.PROTECT, related_name="types"
    )
    tech_level = models.SmallIntegerField(null=True, blank=True)
    meta_level = models.SmallIntegerField(null=True, blank=True)
    mass = models.FloatField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True)
    packaged_volume = models.FloatField(null=True, blank=True)
    capacity = models.FloatField(null=True, blank=True)
    portion_size = models.IntegerField(null=True, blank=True)
    base_price = models.FloatField(null=True, blank=True)
    market_group_id = models.IntegerField(null=True, blank=True)
    variation_parent_type_id = models.IntegerField(null=True, blank=True)
    icon_id = models.IntegerField(null=True, blank=True)
    graphic_id = models.IntegerField(null=True, blank=True)

    if TYPE_CHECKING:  # <fk>_id attributes, for the type checker only
        group_id: int
        faction_id: int | None
        meta_group_id: int | None
        race_id: int | None

    class Meta:
        db_table = "sde_eve_type"
        indexes = [models.Index(fields=["name"], name="sde_eve_type_name_idx")]

    def __str__(self) -> str:
        return self.name
