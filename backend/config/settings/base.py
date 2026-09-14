from pathlib import Path

from environs import Env

from apps.sde import constants as sde_constants

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = Env()
env.read_env(str(BASE_DIR / ".env"), recurse=False)
env.read_env(str(BASE_DIR.parent / "deploy" / ".env"), recurse=False)

SECRET_KEY = env.str("SECRET_KEY", "dev-insecure-secret-key")
DEBUG: bool = False
ALLOWED_HOSTS: list[str] = env.list("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
DOMAIN = env.str("DOMAIN", "localhost")
APP_VERSION = env.str("APP_VERSION", "dev")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "channels",
    "ninja",
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.sde",
    "apps.rules",
    "apps.library",
    # Phase 2: apps.sessions
    # Phase 3: apps.analytics, apps.importer
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.dj_db_url("DATABASE_URL", "postgres://attool:attool@localhost:5433/attool")
}
# Under ASGI every request runs in its own async context, so persistent connections never get
# reused; a psycopg pool makes the per-request connection cheap instead.
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"].setdefault("OPTIONS", {})["pool"] = {"min_size": 1, "max_size": 8}
# Fail fast when the database is down instead of hanging a request or a test run.
DATABASES["default"]["OPTIONS"]["connect_timeout"] = 5

REDIS_URL = env.str("REDIS_URL", "redis://localhost:6380/0")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/auth/login"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 14 * 24 * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to send X-CSRFToken

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(exist_ok=True)  # whitenoise warns loudly if it is missing in dev/test
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- EVE SSO / ESI (used from Phase 0 onwards) ----
EVE_SSO_DISCOVERY_URL = env.str(
    "EVE_SSO_DISCOVERY_URL", "https://login.eveonline.com/.well-known/oauth-authorization-server"
)
EVE_SSO_ISSUERS = ["https://login.eveonline.com", "login.eveonline.com"]
EVE_CLIENT_ID = env.str("EVE_CLIENT_ID", "")
EVE_CLIENT_SECRET = env.str("EVE_CLIENT_SECRET", "")
EVE_SSO_SCOPES = env.list("EVE_SSO_SCOPES", ["publicData"])
# Explicit redirect URI; when empty it is built from the request host, which dev proxies rewrite.
EVE_CALLBACK_URL = env.str("EVE_CALLBACK_URL", "")
ESI_BASE_URL = env.str("ESI_BASE_URL", "https://esi.evetech.net")
ESI_COMPAT_DATE = env.str("ESI_COMPAT_DATE", "2026-08-01")
ESI_CONTACT_EMAIL = env.str("ESI_CONTACT_EMAIL", "")
ESI_USER_AGENT = (
    f"attool/{APP_VERSION} ({ESI_CONTACT_EMAIL}; +https://github.com/spudsattool/attool)"
)

# ---- Instance data (downloads, drop folders); a Docker volume in production ----
INSTANCE_DIR = env.path("INSTANCE_DIR", BASE_DIR / "instance")
SDE_DIR = INSTANCE_DIR / "sde"
SDE_INCLUDED_FILES = env.list("SDE_INCLUDED_FILES", sde_constants.DEFAULT_INCLUDED_FILES)
SDE_TYPE_CATEGORIES = env.list(
    "SDE_TYPE_CATEGORIES", sde_constants.DEFAULT_TYPE_CATEGORIES, subcast=int
)
SDE_AUTO_DOWNLOAD = env.bool("SDE_AUTO_DOWNLOAD", True)
SDE_STALE_DAYS = env.int("SDE_STALE_DAYS", 45)
SDE_LATEST_URL = env.str(
    "SDE_LATEST_URL", "https://developers.eveonline.com/static-data/tranquility/latest.jsonl"
)
SDE_DOWNLOAD_URL = env.str(
    "SDE_DOWNLOAD_URL",
    "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip",
)

RULESET_FIXTURES_DIR = BASE_DIR / "fixtures" / "rulesets"

TEAM_NAME = env.str("TEAM_NAME", "AT Team")
# Characters that are granted admin on login. Empty means nobody can be admitted.
ADMIN_CHARACTER_IDS = env.list("ADMIN_CHARACTER_IDS", [], subcast=int)
# /auth/dev-login shortcut for local work and tests; dev and test settings turn it on.
DEV_LOGIN_ENABLED: bool = False
FIELD_ENCRYPTION_KEY = env.str("FIELD_ENCRYPTION_KEY", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env.str("DJANGO_LOG_LEVEL", "INFO")},
}
