from django.conf import settings
from django.db import connection
from ninja import NinjaAPI, Schema, Status
from ninja.security import django_auth

from accounts.api import router as auth_router
from accounts.api import me_router
from geo.api import router as geo_router
from places.api import router as places_router
from visits.api import router as visits_router

api = NinjaAPI(
    title="Goshuinchō API",
    version="1",
    auth=django_auth,
    urls_namespace="api",
)


class HealthOut(Schema):
    status: str
    version: str


@api.get("/health", auth=None, response={200: HealthOut, 503: HealthOut})
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return Status(503, {"status": "db_unavailable", "version": settings.VERSION})
    return {"status": "ok", "version": settings.VERSION}


api.add_router("/auth", auth_router)
api.add_router("/me", me_router)
api.add_router("/", geo_router)
api.add_router("/", places_router)
api.add_router("/", visits_router)
