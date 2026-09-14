from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only record of significant actions: who did what to which object, and why."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_name = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True, db_index=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_label = models.CharField(max_length=200, blank=True)
    reason = models.TextField(blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-at", "-id"]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.actor_name} {self.action} {self.target_label}"
