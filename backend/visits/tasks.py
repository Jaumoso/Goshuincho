import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from procrastinate.contrib.django import app

from . import media as storage
from .models import Media, Stamp, StampMedia, Visit, VisitMedia

logger = logging.getLogger(__name__)

TRASH_DAYS = 30
ORPHAN_HOURS = 24


@app.task(queue="media")
def make_variants(media_id: str):
    item = Media.objects.filter(id=media_id).first()
    if item:
        storage.ensure_variants(item)


@app.periodic(cron="17 3 * * *")
@app.task(queue="maintenance")
def purge_trash(timestamp: int):
    limit = timezone.now() - timedelta(days=TRASH_DAYS)
    with transaction.atomic():
        stamps, _ = Stamp.objects.filter(deleted_at__lt=limit).delete()
        visits, _ = Visit.objects.filter(deleted_at__lt=limit).delete()
    logger.info("Papelera: %s goshuin y %s visitas purgados", stamps, visits)


@app.periodic(cron="37 3 * * *")
@app.task(queue="maintenance")
def cleanup_orphan_media(timestamp: int):
    limit = timezone.now() - timedelta(hours=ORPHAN_HOURS)
    orphans = Media.objects.filter(created_at__lt=limit).filter(
        ~Exists(StampMedia.objects.filter(media=OuterRef("pk"))),
        ~Exists(VisitMedia.objects.filter(media=OuterRef("pk"))),
    )
    count = 0
    for item in orphans.iterator():
        item.delete()
        storage.delete_files(item)
        count += 1
    logger.info("Imágenes sin enlace borradas: %s", count)
