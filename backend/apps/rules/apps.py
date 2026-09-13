from django.apps import AppConfig


class RulesConfig(AppConfig):
    name = "apps.rules"
    label = "rules"
    verbose_name = "Tournament rules"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (connects revision bumps)
