from django.contrib import admin

from .models import Fit


@admin.register(Fit)
class FitAdmin(admin.ModelAdmin):
    list_display = ("ship", "name", "status", "dps", "ehp_k", "speed_ms", "has_links", "updated_at")
    list_filter = ("status", "has_links", "stats_parse_ok")
    search_fields = ("name", "ship__name")
    raw_id_fields = ("ship", "created_by", "reviewed_by")
    readonly_fields = ("created_at", "updated_at")
