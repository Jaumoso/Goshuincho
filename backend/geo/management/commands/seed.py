import json
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from geo.models import Area, Prefecture, Region
from places.models import Category

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class Command(BaseCommand):
    help = "Carga regiones, prefecturas (con contornos de Natural Earth), zonas y categorías, y crea el primer administrador."

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help="No toca los datos de referencia si ya hay regiones cargadas.",
        )

    def handle(self, *args, if_empty=False, **options):
        if if_empty and Region.objects.exists():
            self.stdout.write("Datos de referencia ya cargados; se omiten.")
        else:
            self.load_reference()
        if if_empty and Category.objects.exists():
            self.stdout.write("Categorías ya cargadas; se omiten.")
        else:
            self.load_categories()
        self.ensure_admin()

    @transaction.atomic
    def load_reference(self):
        data = json.loads((DATA_DIR / "reference.json").read_text(encoding="utf-8"))
        for row in data["regions"]:
            Region.objects.update_or_create(id=row["id"], defaults=row)

        boundaries = self.load_boundaries()
        for row in data["prefectures"]:
            boundary = boundaries.get(row["iso_code"])
            defaults = {**row, "boundary": boundary}
            if boundary is not None:
                defaults["centroid"] = boundary.point_on_surface
            Prefecture.objects.update_or_create(id=row["id"], defaults=defaults)

        for row in data["areas"]:
            Area.objects.update_or_create(slug=row["slug"], defaults=row)

        self.stdout.write(
            self.style.SUCCESS(
                f"Cargadas {len(data['regions'])} regiones, {len(data['prefectures'])} prefecturas "
                f"({len(boundaries)} con contorno) y {len(data['areas'])} zonas."
            )
        )

    @transaction.atomic
    def load_categories(self):
        path = Path(__file__).resolve().parents[3] / "places" / "data" / "categories.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            Category.objects.update_or_create(slug=row["slug"], defaults=row)
        self.stdout.write(self.style.SUCCESS(f"Cargadas {len(rows)} categorías."))

    def load_boundaries(self):
        collection = json.loads((DATA_DIR / "prefectures.geojson").read_text(encoding="utf-8"))
        result = {}
        for feature in collection["features"]:
            geom = GEOSGeometry(json.dumps(feature["geometry"]), srid=4326)
            if not geom.valid:
                geom = geom.make_valid()
            if geom.geom_type == "Polygon":
                geom = MultiPolygon(geom, srid=4326)
            elif geom.geom_type != "MultiPolygon":
                polys = [g for g in geom if g.geom_type in ("Polygon", "MultiPolygon")]
                flat = [p for g in polys for p in (g if g.geom_type == "MultiPolygon" else [g])]
                geom = MultiPolygon(*flat, srid=4326)
            result[feature["properties"]["iso_code"]] = geom
        return result

    def ensure_admin(self):
        email, password = settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD
        if not email:
            return
        if User.objects.filter(email=User.objects.normalize_email_address(email)).exists():
            return
        if not password:
            self.stderr.write("ADMIN_EMAIL definido sin ADMIN_PASSWORD: no se crea el administrador.")
            return
        User.objects.create_superuser(email, password, display_name="Admin")
        self.stdout.write(self.style.SUCCESS(f"Administrador {email} creado."))
