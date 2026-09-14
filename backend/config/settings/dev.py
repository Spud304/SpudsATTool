from .base import *  # noqa: F403

DEBUG = True
DEV_LOGIN_ENABLED = True
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"]
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
EVE_CALLBACK_URL = EVE_CALLBACK_URL or "http://localhost:5173/auth/callback"  # noqa: F405
