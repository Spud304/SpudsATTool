from django.contrib import admin

from .models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "alliance_id", "pilots_can_score", "pilots_can_browse_library")
