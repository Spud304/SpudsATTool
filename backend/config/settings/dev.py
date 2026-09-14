from .base import *  # noqa: F403

DEBUG = True
DEV_LOGIN_ENABLED = True
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"]
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
# 127.0.0.1, not localhost: the browser must use the same host as the callback for the session
# cookie to match, and an explicit IP skips the ::1 / 127.0.0.1 resolution stall in Chrome.
EVE_CALLBACK_URL = EVE_CALLBACK_URL or "http://127.0.0.1:5173/auth/callback"  # noqa: F405
# Logs total vs SQL time per request in the uvicorn console; dev only.
MIDDLEWARE = ["apps.core.middleware.RequestTimingMiddleware", *MIDDLEWARE]  # noqa: F405
