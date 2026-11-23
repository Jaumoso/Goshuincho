import csv
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from geo.models import Prefecture
from geo.utils import prefecture_for_point
from places.models import Category, Place, PlaceCategory, PlaceKind, PlaceSource

COLUMNS = ["kind", "name_ja", "name_romaji", "name_en", "prefecture", "lat", "lon", "categories"]
SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_places.csv"


def find_prefecture(value: str) -> Prefecture | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return Prefecture.objects.filter(id=int(value)).first()
    return Prefecture.objects.filter(
        Q(iso_code__iexact=value)
        | Q(name_ja=value)
        | Q(name_romaji__iexact=value)
        | Q(name_en__iexact=value)
        | Q(name_es__iexact=value)
    ).first()


class Command(BaseCommand):
    help = (
        "Importa lugares desde un CSV con columnas "
        "kind, name_ja, name_romaji, name_en, prefecture, lat, lon, categories. "
        "categories admite 'slug' o 'slug:orden' separados por ';'. "
        "Reimportar actualiza los lugares con el mismo tipo, nombre y prefectura."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", help="Fichero CSV (UTF-8).")
        parser.add_argument("--sample", action="store_true", help="Importa el CSV de muestra incluido.")

    def handle(self, *args, path=None, sample=False, **options):
        if sample:
            path = SAMPLE
        if not path:
            raise CommandError("Indica un fichero CSV o --sample.")
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = set(COLUMNS[:5]) - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"Faltan columnas: {', '.join(sorted(missing))}")
            created, updated = self.import_rows(reader)
        self.stdout.write(self.style.SUCCESS(f"Lugares creados: {created}; actualizados: {updated}."))

    @transaction.atomic
    def import_rows(self, reader):
        created = updated = 0
        for line, row in enumerate(reader, start=2):
            row = {k: (v or "").strip() for k, v in row.items() if k}
            kind = row.get("kind", "")
            if kind not in PlaceKind.values:
                raise CommandError(f"Línea {line}: tipo desconocido '{kind}'.")
            names = {f: row.get(f) or None for f in ("name_ja", "name_romaji", "name_en")}
            if not any(names.values()):
                raise CommandError(f"Línea {line}: falta el nombre.")
            location = None
            if row.get("lat") and row.get("lon"):
                location = Point(float(row["lon"]), float(row["lat"]), srid=4326)
            prefecture = find_prefecture(row.get("prefecture", ""))
            if prefecture is None and location is not None:
                prefecture = prefecture_for_point(location.x, location.y)
            if prefecture is None:
                raise CommandError(f"Línea {line}: no se pudo determinar la prefectura.")

            key = {"kind": kind, "prefecture": prefecture, "osm_id__isnull": True}
            if names["name_ja"]:
                key["name_ja"] = names["name_ja"]
            else:
                key.update({f: v for f, v in names.items() if v})
            place = Place.objects.filter(**key).first()
            fields = {**names, "kind": kind, "prefecture": prefecture, "location": location}
            if place:
                for f, v in fields.items():
                    setattr(place, f, v)
                place.save()
                updated += 1
            else:
                place = Place.objects.create(**fields, source=PlaceSource.CSV)
                created += 1

            for item in filter(None, (c.strip() for c in row.get("categories", "").split(";"))):
                slug, _, seq = item.partition(":")
                category = Category.objects.filter(slug=slug).first()
                if category is None:
                    raise CommandError(f"Línea {line}: categoría desconocida '{slug}'.")
                PlaceCategory.objects.update_or_create(
                    place=place, category=category, defaults={"seq": int(seq) if seq else None}
                )
        return created, updated
