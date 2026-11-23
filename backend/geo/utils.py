from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point

from geo.models import Prefecture


def prefecture_for_point(lon: float, lat: float) -> Prefecture | None:
    """Prefectura que contiene el punto; si cae fuera de los contornos simplificados, la más cercana."""
    point = Point(lon, lat, srid=4326)
    found = Prefecture.objects.filter(boundary__intersects=point).first()
    if found:
        return found
    return (
        Prefecture.objects.filter(boundary__isnull=False)
        .annotate(d=Distance("boundary", point))
        .order_by("d")
        .first()
    )
