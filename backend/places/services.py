from django.db import transaction
from django.db.models import Q

from visits.models import Visit

from .models import Place, PlaceCategory, ReviewStatus, UserPlace


class MergeError(ValueError):
    pass


@transaction.atomic
def merge_place(source: Place, target: Place) -> Place:
    """Fusiona `source` en `target`: visitas (y sus goshuin), datos personales y categorías pasan al destino."""
    source = Place.objects.select_for_update().get(pk=source.pk)
    target = Place.objects.select_for_update().get(pk=target.pk)
    if source.pk == target.pk:
        raise MergeError("No se puede fusionar un lugar consigo mismo.")
    if target.status in (ReviewStatus.MERGED, ReviewStatus.REJECTED):
        raise MergeError("El destino está fusionado o rechazado.")
    if source.status == ReviewStatus.MERGED:
        raise MergeError("El lugar ya estaba fusionado.")

    # stamps_visit_fk tiene ON UPDATE CASCADE: los goshuin siguen a su visita.
    Visit.objects.filter(place=source).update(place=target)

    existing = {up.user_id: up for up in UserPlace.objects.filter(place=target)}
    for up in UserPlace.objects.filter(place=source):
        dest = existing.get(up.user_id)
        if dest is None:
            UserPlace.objects.create(
                user_id=up.user_id, place=target, wishlist=up.wishlist, favorite=up.favorite, notes=up.notes
            )
        else:
            notes = "\n\n".join(n for n in (dest.notes, up.notes) if n) or None
            UserPlace.objects.filter(user_id=up.user_id, place=target).update(
                wishlist=dest.wishlist or up.wishlist, favorite=dest.favorite or up.favorite, notes=notes
            )
    UserPlace.objects.filter(place=source).delete()

    linked = set(PlaceCategory.objects.filter(place=target).values_list("category_id", flat=True))
    for pc in PlaceCategory.objects.filter(place=source):
        if pc.category_id not in linked:
            PlaceCategory.objects.create(place=target, category_id=pc.category_id, seq=pc.seq)
    PlaceCategory.objects.filter(place=source).delete()

    Place.objects.filter(merged_into=source).update(merged_into=target)
    if target.status == ReviewStatus.PENDING and source.status == ReviewStatus.APPROVED:
        target.status = ReviewStatus.APPROVED
        target.save(update_fields=["status", "updated_at"])
    Place.objects.filter(pk=source.pk).update(status=ReviewStatus.MERGED, merged_into=target)
    return target


def merge_candidates(place: Place, limit: int = 5):
    from .api import similar_queryset

    qs = Place.objects.filter(status=ReviewStatus.APPROVED).filter(~Q(pk=place.pk))
    name = place.name_ja or place.name_romaji or place.name_en or ""
    loc = place.location
    return list(similar_queryset(qs, name, loc.y if loc else None, loc.x if loc else None)[:limit])


class CorrectionError(ValueError):
    pass


@transaction.atomic
def apply_correction(correction, reviewer) -> Place:
    """Aplica una propuesta pendiente al lugar y la marca como aplicada."""
    from django.utils import timezone
    from ninja.errors import HttpError

    from .api import apply_patch
    from .models import PlaceCorrection

    correction = PlaceCorrection.objects.select_for_update().get(pk=correction.pk)
    if correction.status != PlaceCorrection.Status.PENDING:
        raise CorrectionError("La propuesta ya estaba revisada.")
    place = Place.objects.select_for_update().get(pk=correction.place_id)
    if place.status != ReviewStatus.APPROVED:
        raise CorrectionError("El lugar ya no está aprobado.")
    try:
        apply_patch(place, correction.changes)
    except HttpError as e:
        raise CorrectionError(f"Datos no válidos: {e}") from e
    if correction.changes:
        # Evita que una reimportación de OSM deshaga la corrección.
        place.locally_modified = True
    place.save()
    correction.status = PlaceCorrection.Status.APPLIED
    correction.reviewed_by = reviewer
    correction.reviewed_at = timezone.now()
    correction.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return place


def reject_correction(correction, reviewer):
    from django.utils import timezone

    from .models import PlaceCorrection

    return PlaceCorrection.objects.filter(pk=correction.pk, status=PlaceCorrection.Status.PENDING).update(
        status=PlaceCorrection.Status.REJECTED, reviewed_by=reviewer, reviewed_at=timezone.now()
    )
