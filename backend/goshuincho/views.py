from django.conf import settings
from django.http import FileResponse, HttpResponseNotFound


def spa(request):
    """Devuelve index.html de la PWA para cualquier ruta del cliente (React Router)."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        return HttpResponseNotFound("La PWA no está compilada (frontend/dist/index.html).")
    response = FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
