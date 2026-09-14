from ninja import NinjaAPI
from ninja.security import django_auth

from apps.accounts.api import router as accounts_router
from apps.audit.api import router as audit_router
from apps.core.api import router as core_router
from apps.library.api import router as library_router
from apps.rules.api import router as rules_router

# django_auth is cookie-based, so ninja enforces CSRF on unsafe methods automatically.
api = NinjaAPI(
    title="AT Tool API",
    version="0.1.0",
    auth=django_auth,
    urls_namespace="api",
)

api.add_router("/", core_router)
api.add_router("/", accounts_router)
api.add_router("/audit", audit_router)
api.add_router("/rulesets", rules_router)
api.add_router("/fits", library_router)
