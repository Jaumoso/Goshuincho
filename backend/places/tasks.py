from procrastinate.contrib.django import app

from .models import OsmImport
from .osm import run_import


@app.task(queue="osm", lock="osm-import")
def import_osm(import_id: int):
    job = OsmImport.objects.select_related("region").filter(id=import_id).first()
    if job and job.status == OsmImport.Status.QUEUED:
        run_import(job)
