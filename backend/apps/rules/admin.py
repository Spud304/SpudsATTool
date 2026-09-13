from django.contrib import admin
from django.http import HttpResponse

from .exporter import export_ruleset
from .models import (
    BannedModuleType,
    GroupLimit,
    GroupLimitMember,
    HullSizeRule,
    ModuleRule,
    PointTableEntry,
    PointTableVersion,
    Ruleset,
    RulesetShip,
    ShipClass,
    Stage,
    TextSection,
    Tournament,
)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "year", "organiser", "server", "verified")
    list_filter = ("organiser", "server", "verified")
    search_fields = ("code", "name")


class HullSizeRuleInline(admin.TabularInline):
    model = HullSizeRule
    extra = 0


class StageInline(admin.TabularInline):
    model = Stage
    extra = 0


class TextSectionInline(admin.StackedInline):
    model = TextSection
    extra = 0


class ModuleRuleInline(admin.StackedInline):
    model = ModuleRule
    extra = 0
    filter_horizontal = ("groups", "categories", "allowed_meta_groups")


@admin.action(description="Export selected rulesets as YAML")
def export_yaml(modeladmin, request, queryset):
    body = "\n---\n".join(export_ruleset(r) for r in queryset.select_related("tournament"))
    response = HttpResponse(body, content_type="text/yaml; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="rulesets.yaml"'
    return response


@admin.register(Ruleset)
class RulesetAdmin(admin.ModelAdmin):
    list_display = (
        "tournament",
        "fielded_pilots",
        "point_cap",
        "duplicate_inflation_mode",
        "revision",
        "imported_at",
    )
    list_select_related = ("tournament",)
    readonly_fields = ("revision", "source_hash", "imported_at")
    filter_horizontal = ("flagship_eligible_meta_groups",)
    inlines = [HullSizeRuleInline, StageInline, ModuleRuleInline, TextSectionInline]
    actions = [export_yaml]


class GroupLimitMemberInline(admin.TabularInline):
    model = GroupLimitMember
    extra = 0
    autocomplete_fields = ("ship", "ship_class")


@admin.register(GroupLimit)
class GroupLimitAdmin(admin.ModelAdmin):
    list_display = ("label", "ruleset", "max")
    list_select_related = ("ruleset__tournament",)
    inlines = [GroupLimitMemberInline]


@admin.register(ShipClass)
class ShipClassAdmin(admin.ModelAdmin):
    list_display = ("name", "ruleset", "hull_size", "active", "sort_order")
    list_filter = ("ruleset", "hull_size", "active")
    search_fields = ("name",)
    list_select_related = ("ruleset__tournament",)


@admin.register(RulesetShip)
class RulesetShipAdmin(admin.ModelAdmin):
    list_display = (
        "ship",
        "ruleset",
        "ship_class",
        "hull_size",
        "legality",
        "flagship_eligible",
        "is_unique",
        "mapping_source",
    )
    list_filter = ("ruleset", "legality", "hull_size", "mapping_source", "is_unique")
    search_fields = ("ship__name", "ship_class__name")
    autocomplete_fields = ("ship", "ship_class")
    list_select_related = ("ship", "ship_class", "ruleset__tournament")


class PointTableEntryInline(admin.TabularInline):
    model = PointTableEntry
    extra = 0
    autocomplete_fields = ("ship", "ship_class")


@admin.register(PointTableVersion)
class PointTableVersionAdmin(admin.ModelAdmin):
    list_display = (
        "ruleset",
        "purpose",
        "version_no",
        "is_current",
        "label",
        "effective_from",
        "imported_at",
    )
    list_filter = ("ruleset", "purpose", "is_current")
    list_select_related = ("ruleset__tournament",)
    inlines = [PointTableEntryInline]


@admin.register(BannedModuleType)
class BannedModuleTypeAdmin(admin.ModelAdmin):
    list_display = ("type", "ruleset")
    autocomplete_fields = ("type",)
    list_select_related = ("type", "ruleset__tournament")
