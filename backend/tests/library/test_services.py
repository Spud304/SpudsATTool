import pytest

from apps.accounts.models import User
from apps.library import services
from apps.library.eft import parse_eft
from apps.library.models import FitStatus
from apps.rules import adapters
from apps.rules.engine import codes as c
from apps.rules.models import BannedModuleType, ModuleRule, ModuleRuleScope

from .conftest import ABSO_FIT, ABSO_PYFA

pytestmark = pytest.mark.django_db


def test_resolve_fit_case_insensitive_and_unresolved(library_sde):
    text = ABSO_FIT.replace("Stasis Webifier II", "stasis webifier ii") + "Mystery Module x2\n"
    resolved = services.resolve_fit(parse_eft(text))
    assert resolved.hull is not None and resolved.hull.name == "Absolution"
    assert resolved.unresolved == ["Mystery Module"]
    web = next(r for r in resolved.items if r.item.name == "stasis webifier ii")
    assert web.type is not None and web.type.pk == 990002
    assert resolved.has_links
    specs = services.item_specs(resolved)
    charge = next(s for s in specs if s.name == "Imperial Navy Multifrequency M")
    assert charge.category_id == 8 and charge.meta_group_id == 4


def test_resolve_hull_ignores_modules(library_sde):
    assert services.resolve_hull("Stasis Webifier II") is None
    assert services.resolve_hull("absolution") is not None


@pytest.fixture
def actor(db):
    return User.objects.create(username="char:1", display_name="Pilot")


def test_create_and_derived(library_sde, actor):
    fit = services.create_fit(actor, eft_text=ABSO_FIT, pyfa_summary=ABSO_PYFA)
    assert fit.status == FitStatus.SUGGESTED and fit.name == "Octo Ewar Abso"
    assert fit.has_links and fit.stats_parse_ok and fit.dps == 709 and fit.ehp_k == 97.6
    assert fit.unresolved_names == []
    with pytest.raises(services.FitError) as exc:
        services.create_fit(actor, eft_text=ABSO_FIT)
    assert exc.value.status == 409


def test_create_rejects_unknown_hull_and_missing_header(library_sde, actor):
    with pytest.raises(services.FitError) as exc:
        services.create_fit(actor, eft_text="[Nonexistent Hull, x]\nStasis Webifier II\n")
    assert exc.value.status == 422
    with pytest.raises(services.FitError):
        services.create_fit(actor, eft_text="Stasis Webifier II\n")


def test_update_hull_mismatch(library_sde, actor):
    fit = services.create_fit(actor, eft_text=ABSO_FIT)
    with pytest.raises(services.FitError) as exc:
        services.update_fit(actor, fit, eft_text="[Rifter, r]\nStasis Webifier II\n")
    assert exc.value.status == 422 and "Rifter" in str(exc.value)


def test_module_rules_adapter_and_cache(imported_atxxii):
    ruleset, _ = imported_atxxii
    spec = adapters.module_rules_for(ruleset)
    assert spec.default_allowed_meta_group_ids == frozenset({1, 2})
    assert len(spec.by_group) == 1 and spec.by_group[0].max_meta_level == 4
    assert spec.by_group[0].hull_scope == "bonused_only" and 208 in spec.by_group[0].group_ids
    assert spec.flagship is not None and 4 in spec.flagship.allowed_meta_group_ids
    assert spec.banned_group_ids == frozenset({303}) and spec.group_names[303] == "Booster"
    assert adapters.module_rules_for(ruleset) is spec
    ModuleRule.objects.create(ruleset=ruleset, scope=ModuleRuleScope.GROUP, max_meta_level=2)
    ruleset.refresh_from_db()
    assert adapters.module_rules_for(ruleset) is not spec


def test_evaluate_fit_against_atxxii(library_sde, imported_atxxii, actor):
    ruleset, _ = imported_atxxii
    fit = services.create_fit(actor, eft_text=ABSO_FIT)
    ev = services.evaluate_fit(fit, ruleset)
    assert ev.is_legal
    assert {v.code for v in ev.violations} == {c.META_LEVEL_TOO_HIGH}  # damp meta 5 on bonused_only

    faction = ABSO_FIT.replace("Stasis Webifier II", "Federation Navy Stasis Webifier")
    services.update_fit(actor, fit, eft_text=faction)
    ev = services.evaluate_fit(fit, ruleset)
    assert not ev.is_legal and c.META_GROUP_NOT_ALLOWED in {v.code for v in ev.violations}
    assert services.evaluate_fit(fit, ruleset, is_flagship=True).is_legal

    drugged = faction.replace("Nanite Repair Paste x500", "Standard Blue Pill Booster x1")
    services.update_fit(actor, fit, eft_text=drugged)
    ev = services.evaluate_fit(fit, ruleset, is_flagship=True)
    assert not ev.is_legal and c.BANNED_GROUP in {v.code for v in ev.violations}

    BannedModuleType.objects.create(ruleset=ruleset, type_id=990007)
    ruleset.refresh_from_db()
    ev = services.evaluate_fit(fit, ruleset)
    banned = next(v for v in ev.violations if v.code == c.BANNED_TYPE)
    assert "Warrior II" in banned.message
