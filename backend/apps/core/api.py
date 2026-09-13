from django.conf import settings
from django.db import connection
from django.http import HttpRequest
from ninja import Router, Schema

router = Router(tags=["core"])


class HealthOut(Schema):
    status: str
    version: str
    database: str


@router.get("/health", auth=None, response=HealthOut)
def health(request: HttpRequest):
    database = "ok"
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:  # pragma: no cover - only on a broken deployment
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": settings.APP_VERSION,
        "database": database,
    }
