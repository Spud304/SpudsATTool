from django.contrib import admin

from .models import (
    Assignment,
    Ban,
    ChangeEvent,
    Opponent,
    Pilot,
    Round,
    Session,
    SessionAttendance,
    Set,
    WarpInLabel,
)


@admin.register(Pilot)
class PilotAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "status", "is_merc", "roles_text")
    list_filter = ("status", "is_merc")
    search_fields = ("name",)
    raw_id_fields = ("user",)


@admin.register(Opponent)
class OpponentAdmin(admin.ModelAdmin):
    list_display = ("name", "alliance_id", "is_active")
    search_fields = ("name",)


@admin.register(WarpInLabel)
class WarpInLabelAdmin(admin.ModelAdmin):
    list_display = ("label", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")


class AttendanceInline(admin.TabularInline):
    model = SessionAttendance
    extra = 0
    raw_id_fields = ("pilot", "removed_by")


class SetInline(admin.TabularInline):
    model = Set
    extra = 0
    fields = ("index", "label", "comp", "our_side")
    raw_id_fields = ("comp",)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "kind", "opponent", "ruleset", "is_archived", "event_seq")
    list_filter = ("kind", "is_archived", "ruleset")
    search_fields = ("title",)
    raw_id_fields = ("opponent", "created_by", "stage", "point_table_version")
    inlines = [AttendanceInline, SetInline]


class BanInline(admin.TabularInline):
    model = Ban
    extra = 0
    raw_id_fields = ("ship",)


class RoundInline(admin.TabularInline):
    model = Round
    extra = 0


@admin.register(Set)
class SetAdmin(admin.ModelAdmin):
    list_display = ("session", "index", "label", "comp", "our_side")
    raw_id_fields = ("comp", "our_archetype", "opp_archetype")
    inlines = [BanInline, RoundInline]


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    raw_id_fields = ("pilot", "ship", "fit")


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("set", "round_no", "outcome")
    inlines = [AssignmentInline]


@admin.register(ChangeEvent)
class ChangeEventAdmin(admin.ModelAdmin):
    list_display = ("session", "seq", "kind", "actor", "at")
    list_filter = ("kind",)
    readonly_fields = ("payload",)
