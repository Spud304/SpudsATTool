from django.contrib import admin
from django.urls import include, path

from apps.scrims.stream import events_view
from config.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/scrims/<int:session_id>/events", events_view, name="scrim-events"),
    path("api/", api.urls),
    path("auth/", include("apps.accounts.urls")),
]
