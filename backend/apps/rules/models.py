"""Tournament rulesets. Written by the YAML importer (and Django admin); read by the engine adapters."""

from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q

from apps.sde.models import EveCategory, EveGroup, EveMetaGroup, EveType

if TYPE_CHECKING:
    from django_stubs_ext.db.models.manager import RelatedManager


class HullSize(models.TextChoices):
    FLAG = "FLAG", "Flagship"
    BS = "BS", "Battleship"
    BC = "BC", "Battlecruiser"
    CR = "CR", "Cruiser"
    LC = "LC", "Logistics Cruiser"
    DE = "DE", "Destroyer"
    FR = "FR", "Frigate"
    LF = "LF", "Logistics Frigate"
    IN = "IN", "Industrial"
    CV = "CV", "Corvette"


class Organiser(models.TextChoices):
    CCP = "ccp", "CCP"
    COMMUNITY = "community", "Community"


class Server(models.TextChoices):
    TRANQUILITY = "tranquility", "Tranquility"
    THUNDERDOME = "thunderdome", "Thunderdome"


class InflationMode(models.TextChoices):
    PER_COPY_ALL = "per_copy_all", "Every copy pays (copies - 1) x surcharge"
    ESCALATING = "escalating", "Copy N pays (N - 1) x surcharge"
    FLAT_ADDITIONAL = "flat_additional", "Every extra copy pays the surcharge once"


class KillPointsSource(models.TextChoices):
    COMP_COST = "comp_cost", "Comp cost"
    KILL_TABLE = "kill_table", "Separate kill table"


class Tiebreak(models.TextChoices):
    NONE = "none", "None"
    POTENTIAL_DPS = "potential_dps_t0", "Potential DPS at t=0"
    POINTS_REMAINING = "points_remaining", "Points remaining"
    CUSTOM = "custom", "Custom"


class ShipsInference(models.TextChoices):
    NONE = "none", "None"
    PREFIX = "prefix", "Hull-prefixed class names"
    PREFIX_AND_ALIASES = "prefix_and_aliases", "Prefixes and group aliases"


class Legality(models.TextChoices):
    LEGAL = "legal", "Legal"
    BANNED = "banned", "Banned"


class MappingSource(models.TextChoices):
    EXPLICIT = "explicit", "Explicit in the document"
    INFERRED_PREFIX = "inferred_prefix", "Inferred from a hull-prefixed class"
    INFERRED_ALIAS = "inferred_alias", "Inferred from a group alias"
    MANUAL = "manual", "Edited in admin"


class BanTargets(models.TextChoices):
    HULL = "hull", "Hull"
    CLASS = "class", "Ship class"


class TablePurpose(models.TextChoices):
    COST = "cost", "Comp cost"
    KILL = "kill", "Kill scoring"


class ModuleRuleScope(models.TextChoices):
    DEFAULT = "default", "Default"
    GROUP = "group", "By group or category"
    FLAGSHIP = "flagship", "Flagship relaxation"


class HullScope(models.TextChoices):
    ANY = "any", "Any hull"
    BONUSED_ONLY = "bonused_only", "Bonused hulls only"


class Tournament(models.Model):
    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=100)
    organiser = models.CharField(max_length=16, choices=Organiser.choices)
    server = models.CharField(max_length=16, choices=Server.choices, default=Server.TRANQUILITY)
    year = models.SmallIntegerField()
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    rules_url = models.URLField(blank=True)
    verified = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rules_tournament"
        ordering = ["-year", "code"]

    def __str__(self) -> str:
        return self.code


class Ruleset(models.Model):
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE, related_name="ruleset")
    fielded_pilots = models.SmallIntegerField()
    point_cap = models.SmallIntegerField()
    max_same_hull = models.SmallIntegerField(null=True, blank=True)
    duplicate_inflation_enabled = models.BooleanField(default=False)
    duplicate_inflation_mode = models.CharField(
        max_length=20, choices=InflationMode.choices, default=InflationMode.PER_COPY_ALL
    )
    flagship_enabled = models.BooleanField(default=False)
    flagship_immune_to_bans = models.BooleanField(default=True)
    flagship_exempt_from_size_limit = models.BooleanField(default=True)
    flagship_counts_for_same_hull = models.BooleanField(default=True)
    flagship_counts_for_inflation = models.BooleanField(default=True)
    flagship_lost_permanently = models.BooleanField(default=True)
    flagship_eligible_sizes = models.JSONField(default=list, blank=True)
    flagship_eligible_meta_groups = models.ManyToManyField(
        EveMetaGroup, blank=True, related_name="+"
    )
    unique_ship_extra_bans = models.SmallIntegerField(default=0)
    unspent_points_to_opponent = models.BooleanField(default=True)
    kill_points_source = models.CharField(
        max_length=16, choices=KillPointsSource.choices, default=KillPointsSource.COMP_COST
    )
    point_threshold = models.IntegerField(null=True, blank=True)
    tiebreak_rule = models.CharField(max_length=20, choices=Tiebreak.choices, default=Tiebreak.NONE)
    roster_max = models.SmallIntegerField(null=True, blank=True)
    merc_max = models.SmallIntegerField(null=True, blank=True)
    ships_inference = models.CharField(
        max_length=20, choices=ShipsInference.choices, default=ShipsInference.PREFIX
    )
    extra = models.JSONField(default=dict, blank=True)
    # Bumped on every import and on child edits; the engine adapter cache is keyed on it.
    revision = models.PositiveIntegerField(default=0)
    source_hash = models.CharField(max_length=64, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)

    if TYPE_CHECKING:  # reverse relations, for the type checker only
        hull_sizes: "RelatedManager[HullSizeRule]"
        group_limits: "RelatedManager[GroupLimit]"
        stages: "RelatedManager[Stage]"
        ship_classes: "RelatedManager[ShipClass]"
        ships: "RelatedManager[RulesetShip]"
        point_versions: "RelatedManager[PointTableVersion]"
        module_rules: "RelatedManager[ModuleRule]"
        banned_module_types: "RelatedManager[BannedModuleType]"
        banned_module_groups: "RelatedManager[BannedModuleGroup]"
        text_sections: "RelatedManager[TextSection]"

    class Meta:
        db_table = "rules_ruleset"

    def __str__(self) -> str:
        return f"{self.tournament.code} rules"

    @property
    def code(self) -> str:
        return self.tournament.code


class HullSizeRule(models.Model):
    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="hull_sizes")
    hull_size = models.CharField(max_length=4, choices=HullSize.choices)
    label = models.CharField(max_length=40)
    max_per_comp = models.SmallIntegerField(null=True, blank=True)
    duplicate_surcharge = models.SmallIntegerField(default=0)
    sort_order = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "rules_hull_size_rule"
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["ruleset", "hull_size"], name="rules_hull_size_uniq"),
            models.CheckConstraint(
                condition=~Q(hull_size="FLAG") | Q(duplicate_surcharge=0),
                name="rules_flag_has_no_surcharge",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label} ({self.hull_size})"


class GroupLimit(models.Model):
    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="group_limits")
    code = models.SlugField(max_length=32)
    label = models.CharField(max_length=80)
    max = models.SmallIntegerField()
    message = models.CharField(max_length=300, blank=True)
    sort_order = models.SmallIntegerField(default=0)

    if TYPE_CHECKING:
        members: "RelatedManager[GroupLimitMember]"
        ruleset_id: int

    class Meta:
        db_table = "rules_group_limit"
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["ruleset", "code"], name="rules_group_limit_uniq")
        ]

    def __str__(self) -> str:
        return self.label


class GroupLimitMember(models.Model):
    limit = models.ForeignKey(GroupLimit, on_delete=models.CASCADE, related_name="members")
    hull_size = models.CharField(max_length=4, choices=HullSize.choices, null=True, blank=True)
    ship_class = models.ForeignKey(
        "ShipClass", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    ship = models.ForeignKey(
        EveType, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    weight = models.SmallIntegerField(default=1)

    if TYPE_CHECKING:
        limit_id: int
        ship_class_id: int | None
        ship_id: int | None

    class Meta:
        db_table = "rules_group_limit_member"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(hull_size__isnull=False, ship_class__isnull=True, ship__isnull=True)
                    | Q(hull_size__isnull=True, ship_class__isnull=False, ship__isnull=True)
                    | Q(hull_size__isnull=True, ship_class__isnull=True, ship__isnull=False)
                ),
                name="rules_group_limit_member_one_selector",
            )
        ]


class Stage(models.Model):
    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="stages")
    code = models.SlugField(max_length=32)
    label = models.CharField(max_length=80, blank=True)
    sort_order = models.SmallIntegerField(default=0)
    best_of = models.SmallIntegerField(default=1)
    bans_per_side = models.SmallIntegerField(default=0)
    ban_order_pattern = models.CharField(max_length=32, blank=True)
    bans_are_blind = models.BooleanField(default=False)
    ban_targets = models.CharField(
        max_length=8, choices=BanTargets.choices, default=BanTargets.HULL
    )
    ban_deadline_minutes = models.SmallIntegerField(null=True, blank=True)
    avalanche_enabled = models.BooleanField(default=False)
    avalanche_loser_bans = models.SmallIntegerField(default=0)
    avalanche_winner_bans = models.SmallIntegerField(default=0)
    avalanche_blind = models.BooleanField(default=True)
    avalanche_persists = models.BooleanField(default=True)
    flagship_uses = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "rules_stage"
        ordering = ["sort_order"]
        constraints = [models.UniqueConstraint(fields=["ruleset", "code"], name="rules_stage_uniq")]

    def __str__(self) -> str:
        return self.label or self.code


class ShipClass(models.Model):
    """One line of the official points list. Never deleted: old point versions reference it."""

    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="ship_classes")
    name = models.CharField(max_length=200)
    hull_size = models.CharField(max_length=4, choices=HullSize.choices)
    sort_order = models.SmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "rules_ship_class"
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["ruleset", "name"], name="rules_ship_class_uniq")
        ]

    def __str__(self) -> str:
        return self.name


class RulesetShip(models.Model):
    """How this ruleset sees one hull."""

    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="ships")
    ship = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="ruleset_entries")
    ship_class = models.ForeignKey(
        ShipClass, null=True, blank=True, on_delete=models.PROTECT, related_name="ships"
    )
    hull_size = models.CharField(max_length=4, choices=HullSize.choices)
    hull_size_is_override = models.BooleanField(default=False)
    legality = models.CharField(max_length=8, choices=Legality.choices, default=Legality.LEGAL)
    flagship_eligible = models.BooleanField(null=True, blank=True)
    is_unique = models.BooleanField(default=False)
    mapping_source = models.CharField(
        max_length=20, choices=MappingSource.choices, default=MappingSource.EXPLICIT
    )
    notes = models.CharField(max_length=200, blank=True)

    if TYPE_CHECKING:
        ruleset_id: int
        ship_id: int
        ship_class_id: int | None

    class Meta:
        db_table = "rules_ruleset_ship"
        constraints = [
            models.UniqueConstraint(fields=["ruleset", "ship"], name="rules_ruleset_ship_uniq")
        ]
        indexes = [
            models.Index(fields=["ruleset", "legality"], name="rules_ruleset_ship_legal_idx")
        ]

    def __str__(self) -> str:
        return f"{self.ship.name} in {self.ruleset.code}"


class PointTableVersion(models.Model):
    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="point_versions")
    purpose = models.CharField(
        max_length=8, choices=TablePurpose.choices, default=TablePurpose.COST
    )
    version_no = models.SmallIntegerField()
    label = models.CharField(max_length=120, blank=True)
    source_url = models.URLField(blank=True)
    effective_from = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    content_hash = models.CharField(max_length=64)
    imported_at = models.DateTimeField()

    if TYPE_CHECKING:
        entries: "RelatedManager[PointTableEntry]"
        ruleset_id: int

    class Meta:
        db_table = "rules_point_table_version"
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["ruleset", "purpose", "version_no"], name="rules_ptv_no_uniq"
            ),
            models.UniqueConstraint(
                fields=["ruleset", "purpose"],
                condition=Q(is_current=True),
                name="rules_ptv_one_current",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ruleset.code} {self.purpose} v{self.version_no}"

    def is_pinned(self) -> bool:
        """Sessions will pin versions; until then nothing references a version from outside rules."""
        return False


class PointTableEntry(models.Model):
    version = models.ForeignKey(PointTableVersion, on_delete=models.CASCADE, related_name="entries")
    ship_class = models.ForeignKey(
        ShipClass, null=True, blank=True, on_delete=models.PROTECT, related_name="point_entries"
    )
    ship = models.ForeignKey(
        EveType, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    points = models.SmallIntegerField()

    if TYPE_CHECKING:
        version_id: int
        ship_class_id: int | None
        ship_id: int | None

    class Meta:
        db_table = "rules_point_table_entry"
        constraints = [
            models.CheckConstraint(
                condition=Q(ship_class__isnull=False, ship__isnull=True)
                | Q(ship_class__isnull=True, ship__isnull=False),
                name="rules_pte_one_target",
            ),
            models.UniqueConstraint(fields=["version", "ship_class"], name="rules_pte_class_uniq"),
            models.UniqueConstraint(fields=["version", "ship"], name="rules_pte_ship_uniq"),
        ]


class ModuleRule(models.Model):
    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="module_rules")
    scope = models.CharField(max_length=10, choices=ModuleRuleScope.choices)
    sort_order = models.SmallIntegerField(default=0)
    max_meta_level = models.SmallIntegerField(null=True, blank=True)
    hull_scope = models.CharField(max_length=14, choices=HullScope.choices, default=HullScope.ANY)
    groups = models.ManyToManyField(EveGroup, blank=True, related_name="+")
    categories = models.ManyToManyField(EveCategory, blank=True, related_name="+")
    allowed_meta_groups = models.ManyToManyField(EveMetaGroup, blank=True, related_name="+")
    restricts_meta_groups = models.BooleanField(
        default=False,
        help_text="True when allowed_meta_groups applies (an empty M2M is ambiguous otherwise).",
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "rules_module_rule"
        ordering = ["scope", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["ruleset", "scope"],
                condition=Q(scope__in=["default", "flagship"]),
                name="rules_module_rule_singleton_scopes",
            )
        ]


class BannedModuleType(models.Model):
    ruleset = models.ForeignKey(
        Ruleset, on_delete=models.CASCADE, related_name="banned_module_types"
    )
    type = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "rules_banned_module_type"
        constraints = [
            models.UniqueConstraint(fields=["ruleset", "type"], name="rules_banned_module_uniq")
        ]


class BannedModuleGroup(models.Model):
    """Every type in the group is illegal, e.g. Booster (drugs of any sort)."""

    ruleset = models.ForeignKey(
        Ruleset, on_delete=models.CASCADE, related_name="banned_module_groups"
    )
    group = models.ForeignKey(EveGroup, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "rules_banned_module_group"
        constraints = [
            models.UniqueConstraint(fields=["ruleset", "group"], name="rules_banned_group_uniq")
        ]


class TextSection(models.Model):
    ruleset = models.ForeignKey(Ruleset, on_delete=models.CASCADE, related_name="text_sections")
    sort_order = models.SmallIntegerField(default=0)
    heading = models.CharField(max_length=120)
    body_markdown = models.TextField()
    source_url = models.URLField(blank=True)

    class Meta:
        db_table = "rules_text_section"
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.heading
