from django.contrib import admin

from .models import Archetype, Comp, CompSlot, Fit


@admin.register(Fit)
class FitAdmin(admin.ModelAdmin):
    list_display = ("ship", "name", "status", "dps", "ehp_k", "speed_ms", "has_links", "updated_at")
    list_filter = ("status", "has_links", "stats_parse_ok")
    search_fields = ("name", "ship__name")
    raw_id_fields = ("ship", "created_by", "reviewed_by")
    readonly_fields = ("created_at", "updated_at")


class CompSlotInline(admin.TabularInline):
    model = CompSlot
    extra = 0
    raw_id_fields = ("ship", "default_fit")


@admin.register(Comp)
class CompAdmin(admin.ModelAdmin):
    list_display = ("name", "ruleset", "status", "archetype", "updated_at")
    list_filter = ("status", "ruleset", "archetype")
    search_fields = ("name",)
    inlines = [CompSlotInline]
    raw_id_fields = ("created_by", "reviewed_by")


@admin.register(Archetype)
class ArchetypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_retired", "sort_order")
    list_editable = ("is_retired", "sort_order")
