import json

from django.contrib import admin
from django.utils.html import format_html

from .models import EveCategory, EveGroup, EveType, SdeBuild, SdeRawRecord


class ReadOnlyAdmin(admin.ModelAdmin):
    """The SDE mirror is importer-owned; admin is for looking, not editing."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SdeBuild)
class SdeBuildAdmin(ReadOnlyAdmin):
    list_display = (
        "build",
        "release_date",
        "imported_at",
        "last_checked_at",
        "duration_s",
        "source",
    )


@admin.register(EveType)
class EveTypeAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "name",
        "group",
        "meta_group",
        "faction",
        "tech_level",
        "published",
        "removed",
    )
    list_filter = ("published", "removed", "group__category", "meta_group")
    search_fields = ("name", "id")
    list_select_related = ("group", "meta_group", "faction")


@admin.register(EveGroup)
class EveGroupAdmin(ReadOnlyAdmin):
    list_display = ("id", "name", "category", "published", "removed")
    list_filter = ("category", "published", "removed")
    search_fields = ("name",)


@admin.register(EveCategory)
class EveCategoryAdmin(ReadOnlyAdmin):
    list_display = ("id", "name", "published", "removed")


@admin.register(SdeRawRecord)
class SdeRawRecordAdmin(ReadOnlyAdmin):
    list_display = ("file", "key", "build", "removed")
    list_filter = ("file", "removed")
    search_fields = ("key",)
    readonly_fields = ("file", "key", "build", "removed", "pretty_data")
    exclude = ("data",)

    @admin.display(description="data")
    def pretty_data(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.data, indent=2, ensure_ascii=False))
