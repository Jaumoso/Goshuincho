from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from geo.models import Region
from places.models import OsmImport
from places.osm import REGION_EXTRACTS, run_import


class Command(BaseCommand):
    help = (
        "Importa templos, santuarios y estaciones de OpenStreetMap por región, desde los extractos de "
        "Geofabrik. Reimportar actualiza por osm_type + osm_id, respeta los lugares modificados "
        "localmente y marca como osm_missing los que ya no aparecen."
    )

    def add_arguments(self, parser):
        parser.add_argument("regions", nargs="*", help=f"Regiones: {', '.join(REGION_EXTRACTS)} o 'all'.")
        parser.add_argument("--file", type=Path, help="Usa un .osm.pbf ya descargado (solo con una región).")

    def handle(self, *args, regions, file=None, **options):
        if not regions:
            raise CommandError(f"Indica una o más regiones: {', '.join(REGION_EXTRACTS)} o 'all'.")
        slugs = list(REGION_EXTRACTS) if regions == ["all"] else regions
        unknown = set(slugs) - set(REGION_EXTRACTS)
        if unknown:
            raise CommandError(f"Regiones desconocidas: {', '.join(sorted(unknown))}")
        if file and len(slugs) != 1:
            raise CommandError("--file solo se puede usar con una región.")
        for slug in slugs:
            region = Region.objects.get(slug=slug)
            job = OsmImport.objects.create(region=region)
            run_import(job, file, lambda msg: self.stdout.write(f"[{slug}] {msg}"))
            self.stdout.write(self.style.SUCCESS(f"[{slug}] {job.total} elementos; creados {job.created}."))
