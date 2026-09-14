from django.contrib import admin

from .models import AdmissionRule, EveCharacter, Invite, Membership, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("display_name", "username", "is_active", "is_staff", "created_at")
    search_fields = ("display_name", "username")
    readonly_fields = ("password", "last_login", "created_at")


@admin.register(EveCharacter)
class EveCharacterAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "character_id",
        "corporation_id",
        "alliance_id",
        "user",
        "last_login_at",
    )
    search_fields = ("name", "character_id")
    list_select_related = ("user",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "status", "source", "is_leadership", "created_at")
    list_filter = ("role", "status", "source", "is_leadership")
    list_select_related = ("user",)


@admin.register(AdmissionRule)
class AdmissionRuleAdmin(admin.ModelAdmin):
    list_display = ("kind", "entity_id", "entity_name", "default_role", "enabled")
    list_filter = ("kind", "enabled")


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("token", "role", "uses_left", "expires_at", "note", "created_by")
