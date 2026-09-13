from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key"
ALLOWED_HOSTS = ["*"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
# SQLite keeps the skeleton tests free of infrastructure. Set TEST_DATABASE_URL to run
# against Postgres, which the Phase 2 row-locking tests will require.
DATABASES = {
    "default": env.dj_db_url("TEST_DATABASE_URL", "sqlite://:memory:")  # noqa: F405
}
EVE_CLIENT_ID = "test-client-id"
EVE_CLIENT_SECRET = "test-client-secret"
