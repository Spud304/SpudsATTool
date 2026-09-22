"""Bump Ruleset.revision whenever the ruleset or a child row changes, so cached engine inputs invalidate."""

from django.db.models import F
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import (
    BannedModuleGroup,
    BannedModuleType,
    GroupLimit,
    GroupLimitMember,
    HullSizeRule,
    ModuleNamePattern,
    ModuleRule,
    PointTableEntry,
    PointTableVersion,
    Ruleset,
    RulesetShip,
    ShipClass,
    Stage,
    TextSection,
)


def bump_revision(ruleset_id: int | None) -> None:
    if ruleset_id is not None:
        Ruleset.objects.filter(pk=ruleset_id).update(revision=F("revision") + 1)


def _ruleset_id_of(instance) -> int | None:
    if isinstance(instance, Ruleset):
        return instance.pk
    if isinstance(instance, GroupLimitMember):
        return (
            GroupLimit.objects.filter(pk=instance.limit_id)
            .values_list("ruleset_id", flat=True)
            .first()
        )
    if isinstance(instance, PointTableEntry):
        return (
            PointTableVersion.objects.filter(pk=instance.version_id)
            .values_list("ruleset_id", flat=True)
            .first()
        )
    return getattr(instance, "ruleset_id", None)


_CHILD_MODELS = (
    HullSizeRule,
    GroupLimit,
    GroupLimitMember,
    Stage,
    ShipClass,
    RulesetShip,
    PointTableVersion,
    PointTableEntry,
    ModuleRule,
    BannedModuleType,
    BannedModuleGroup,
    ModuleNamePattern,
    TextSection,
)

for _model in _CHILD_MODELS:

    @receiver(post_save, sender=_model, weak=False)
    @receiver(post_delete, sender=_model, weak=False)
    def _on_child_change(sender, instance, **kwargs):
        bump_revision(_ruleset_id_of(instance))


@receiver(post_save, sender=Ruleset, weak=False)
def _on_ruleset_save(sender, instance, **kwargs):
    # The ruleset's own knobs (point cap, max same hull, flagship flags) feed the cached spec too.
    bump_revision(instance.pk)


@receiver(m2m_changed, sender=Ruleset.flagship_eligible_meta_groups.through, weak=False)
@receiver(m2m_changed, sender=ModuleRule.groups.through, weak=False)
@receiver(m2m_changed, sender=ModuleRule.categories.through, weak=False)
@receiver(m2m_changed, sender=ModuleRule.allowed_meta_groups.through, weak=False)
def _on_m2m_change(sender, instance, action, **kwargs):
    if action.startswith("post_"):
        bump_revision(_ruleset_id_of(instance))
