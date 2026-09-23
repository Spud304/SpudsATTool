from ninja import NinjaAPI
from ninja.security import django_auth

from apps.accounts.api import router as accounts_router
from apps.accounts.roles_api import router as roles_router
from apps.audit.api import router as audit_router
from apps.core.api import router as core_router
from apps.library.api import router as library_router
from apps.library.comps_api import router as comps_router
from apps.library.scratchpad_api import router as scratchpad_router
from apps.rules.api import router as rules_router
from apps.scrims.api import opponents_router, pilots_router
from apps.scrims.api import router as scrims_router
from apps.scrims.labels_api import router as labels_router
from apps.scrims.share_api import public_router as share_public_router
from apps.scrims.share_api import router as share_router

# django_auth is cookie-based, so ninja enforces CSRF on unsafe methods automatically.
api = NinjaAPI(
    title="AT Tool API",
    version="0.1.0",
    auth=django_auth,
    urls_namespace="api",
)

api.add_router("/", core_router)
api.add_router("/", accounts_router)
api.add_router("/team/roles", roles_router)
api.add_router("/audit", audit_router)
api.add_router("/rulesets", rules_router)
api.add_router("/fits", library_router)
api.add_router("/comps", comps_router)
api.add_router("/scratchpad", scratchpad_router)
scrims_router.add_router("", share_router)
api.add_router("/scrims", scrims_router)
api.add_router("/share", share_public_router)
api.add_router("/pilots", pilots_router)
api.add_router("/opponents", opponents_router)
api.add_router("/warp-labels", labels_router)
