import uuid
from datetime import date
from typing import Literal, Optional

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.db.models.functions import ExtractYear, TruncMonth
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, File, Form, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile

from places.api import visible_place
from places.models import Place, ReviewStatus

from . import media as storage
from .models import (
    DatePrecision,
    Goshuincho,
    Media,
    MediaRole,
    Stamp,
    StampMedia,
    UserPlaceSummary,
    Visit,
    VisitKind,
    VisitMedia,
)

router = Router(tags=["visits"])

KindLiteral = Literal["in_person", "mail", "event"]
PrecisionLiteral = Literal["day", "month", "season", "year", "unknown"]
StampKindLiteral = Literal["goshuin", "goshuin_limited", "goshuin_seasonal", "station_stamp", "other_stamp"]
MediumLiteral = Literal["jikigaki", "kakioki", "stamped_paper", "digital", "other"]
RoleLiteral = Literal["front", "back", "scan", "detail"]
PAGE_MAX = 100


def today_tokyo() -> date:
    return timezone.localdate()  # TIME_ZONE = Asia/Tokyo


def normalize_date(value: Optional[date], precision: str) -> Optional[date]:
    """Lleva la fecha al primer día del periodo según la precisión y rechaza fechas futuras."""
    if precision == DatePrecision.UNKNOWN:
        return None
    if value is None:
        raise HttpError(422, "date_required")
    if precision == DatePrecision.MONTH:
        value = value.replace(day=1)
    elif precision == DatePrecision.SEASON:
        if value.month in (1, 2):
            value = date(value.year - 1, 12, 1)
        else:
            value = date(value.year, value.month - (value.month % 3), 1)
    elif precision == DatePrecision.YEAR:
        value = date(value.year, 1, 1)
    if value > today_tokyo():
        raise HttpError(422, "date_in_future")
    return value


# --- Esquemas ---------------------------------------------------------------


class MediaOut(Schema):
    id: uuid.UUID
    mime: str
    width: Optional[int]
    height: Optional[int]
    taken_at: Optional[str]
    role: Optional[str] = None


class MediaLink(Schema):
    media_id: uuid.UUID
    role: RoleLiteral = "front"


class PlaceRef(Schema):
    id: uuid.UUID
    kind: str
    name_ja: Optional[str]
    name_romaji: Optional[str]
    name_en: Optional[str]
    prefecture_id: int


class StampOut(Schema):
    id: uuid.UUID
    visit_id: uuid.UUID
    place_id: uuid.UUID
    kind: str
    medium: Optional[str]
    title: Optional[str]
    event_name: Optional[str]
    donation_yen: Optional[int]
    goshuincho_id: Optional[uuid.UUID]
    page_label: Optional[str]
    notes: Optional[str]
    media: list[MediaOut]


class StampWithContext(StampOut):
    place: PlaceRef
    visited_on: Optional[date]
    visited_precision: str
    visit_kind: str


class StampPage(Schema):
    items: list[StampWithContext]
    count: int
    next_offset: Optional[int]


class StampIn(Schema):
    id: Optional[uuid.UUID] = None
    kind: StampKindLiteral = "goshuin"
    medium: Optional[MediumLiteral] = None
    title: Optional[str] = Field(None, max_length=200)
    event_name: Optional[str] = Field(None, max_length=200)
    donation_yen: Optional[int] = Field(None, ge=0)
    goshuincho_id: Optional[uuid.UUID] = None
    page_label: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    media: list[MediaLink] = []


class StampPatch(Schema):
    kind: Optional[StampKindLiteral] = None
    medium: Optional[MediumLiteral] = None
    title: Optional[str] = Field(None, max_length=200)
    event_name: Optional[str] = Field(None, max_length=200)
    donation_yen: Optional[int] = Field(None, ge=0)
    goshuincho_id: Optional[uuid.UUID] = None
    page_label: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    media: Optional[list[MediaLink]] = None


class VisitOut(Schema):
    id: uuid.UUID
    place_id: uuid.UUID
    kind: str
    event_location: Optional[str]
    visited_on: Optional[date]
    visited_precision: str
    notes: Optional[str]
    created_at: str
    stamps: list[StampOut]
    media: list[MediaOut]


class VisitWithPlace(VisitOut):
    place: PlaceRef


class VisitIn(Schema):
    id: Optional[uuid.UUID] = None
    kind: KindLiteral = "in_person"
    event_location: Optional[str] = Field(None, max_length=200)
    visited_on: Optional[date] = None
    visited_precision: PrecisionLiteral = "day"
    notes: Optional[str] = None
    media: list[uuid.UUID] = []
    stamps: list[StampIn] = []


class VisitPatch(Schema):
    kind: Optional[KindLiteral] = None
    event_location: Optional[str] = Field(None, max_length=200)
    visited_on: Optional[date] = None
    visited_precision: Optional[PrecisionLiteral] = None
    notes: Optional[str] = None
    media: Optional[list[uuid.UUID]] = None


class GoshuinchoIn(Schema):
    id: Optional[uuid.UUID] = None
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    started_on: Optional[date] = None
    finished_on: Optional[date] = None


class GoshuinchoPatch(Schema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    started_on: Optional[date] = None
    finished_on: Optional[date] = None


class GoshuinchoOut(Schema):
    id: uuid.UUID
    name: str
    description: Optional[str]
    started_on: Optional[date]
    finished_on: Optional[date]
    stamp_count: int


class CountItem(Schema):
    key: str
    count: int


class StatsOut(Schema):
    places_visited: int
    visits: int
    stamps: int
    goshuin: int
    prefectures_visited: int
    by_prefecture: list[CountItem]
    by_kind: list[CountItem]
    by_year: list[CountItem]


class PrefectureStat(Schema):
    id: int
    places: int
    visited: int
    goshuin: int


class RegionStat(Schema):
    id: int
    places: int
    visited: int


class DayCount(Schema):
    date: date
    count: int


class StatsDetailOut(Schema):
    by_prefecture: list[PrefectureStat]
    by_region: list[RegionStat]
    by_place_kind: list[CountItem]
    goshuin_by_year: list[CountItem]
    longest_streak_months: int
    current_streak_months: int
    heatmap_year: int
    heatmap: list[DayCount]
    years: list[int]


class ErrorOut(Schema):
    detail: str


# --- Serialización ----------------------------------------------------------


def media_out(item: Media, role: Optional[str] = None) -> dict:
    return {
        "id": item.id,
        "mime": item.mime,
        "width": item.width,
        "height": item.height,
        "taken_at": item.taken_at.isoformat() if item.taken_at else None,
        "role": role,
    }


def place_ref(place: Place) -> dict:
    return {
        "id": place.id,
        "kind": place.kind,
        "name_ja": place.name_ja,
        "name_romaji": place.name_romaji,
        "name_en": place.name_en,
        "prefecture_id": place.prefecture_id,
    }


def stamp_out(stamp: Stamp) -> dict:
    links = sorted(stamp.stampmedia_set.all(), key=lambda link: link.position)
    return {
        "id": stamp.id,
        "visit_id": stamp.visit_id,
        "place_id": stamp.place_id,
        "kind": stamp.kind,
        "medium": stamp.medium,
        "title": stamp.title,
        "event_name": stamp.event_name,
        "donation_yen": stamp.donation_yen,
        "goshuincho_id": stamp.goshuincho_id,
        "page_label": stamp.page_label,
        "notes": stamp.notes,
        "media": [media_out(link.media, link.role) for link in links],
    }


def visit_out(visit: Visit, with_place: bool = False) -> dict:
    stamps = [s for s in visit.stamps.all() if s.deleted_at is None]
    stamps.sort(key=lambda s: s.created_at)
    links = sorted(visit.visitmedia_set.all(), key=lambda link: link.position)
    data = {
        "id": visit.id,
        "place_id": visit.place_id,
        "kind": visit.kind,
        "event_location": visit.event_location,
        "visited_on": visit.visited_on,
        "visited_precision": visit.visited_precision,
        "notes": visit.notes,
        "created_at": visit.created_at.isoformat(),
        "stamps": [stamp_out(s) for s in stamps],
        "media": [media_out(link.media) for link in links],
    }
    if with_place:
        data["place"] = place_ref(visit.place)
    return data


def visit_queryset(user):
    return (
        Visit.objects.filter(user=user, deleted_at__isnull=True)
        .select_related("place")
        .prefetch_related("stamps__stampmedia_set__media", "visitmedia_set__media")
        .order_by(F("visited_on").desc(nulls_last=True), "-created_at")
    )


def stamp_queryset(user):
    return (
        Stamp.objects.filter(user=user, deleted_at__isnull=True, visit__deleted_at__isnull=True)
        .select_related("visit", "place")
        .prefetch_related("stampmedia_set__media")
    )


def stamp_with_context(stamp: Stamp) -> dict:
    return {
        **stamp_out(stamp),
        "place": place_ref(stamp.place),
        "visited_on": stamp.visit.visited_on,
        "visited_precision": stamp.visit.visited_precision,
        "visit_kind": stamp.visit.kind,
    }


# --- Validación -------------------------------------------------------------


def own_media(user, ids) -> list[Media]:
    ids = list(dict.fromkeys(ids))
    found = {m.id: m for m in Media.objects.filter(user=user, id__in=ids)}
    if len(found) != len(ids):
        raise HttpError(422, "invalid_media")
    return [found[i] for i in ids]


def check_goshuincho(user, goshuincho_id):
    if goshuincho_id and not Goshuincho.objects.filter(id=goshuincho_id, user=user).exists():
        raise HttpError(422, "invalid_goshuincho")


def apply_visit_fields(visit: Visit, data: dict):
    for f in ("kind", "event_location", "notes", "visited_on", "visited_precision"):
        if f in data:
            setattr(visit, f, data[f])
    if visit.kind != VisitKind.EVENT:
        visit.event_location = None
    else:
        visit.event_location = (visit.event_location or "").strip() or None
    visit.notes = (visit.notes or "").strip() or None
    visit.visited_on = normalize_date(visit.visited_on, visit.visited_precision)


def set_visit_media(visit: Visit, user, ids):
    items = own_media(user, ids)
    VisitMedia.objects.filter(visit=visit).delete()
    VisitMedia.objects.bulk_create(
        [VisitMedia(visit=visit, media=m, position=i) for i, m in enumerate(items)]
    )


def set_stamp_media(stamp: Stamp, user, links: list[dict]):
    items = own_media(user, [link["media_id"] for link in links])
    roles = {link["media_id"]: link.get("role") or MediaRole.FRONT for link in links}
    StampMedia.objects.filter(stamp=stamp).delete()
    StampMedia.objects.bulk_create(
        [StampMedia(stamp=stamp, media=m, role=roles[m.id], position=i) for i, m in enumerate(items)]
    )


def create_stamp(user, visit: Visit, data: dict) -> tuple[Stamp, bool]:
    stamp_id = data.pop("id", None)
    links = data.pop("media", [])
    if stamp_id:
        existing = Stamp.objects.filter(id=stamp_id).first()
        if existing:
            if existing.user_id != user.id:
                raise HttpError(409, "id_conflict")
            return existing, False
    check_goshuincho(user, data.get("goshuincho_id"))
    for f in ("title", "event_name", "page_label", "notes"):
        data[f] = (data.get(f) or "").strip() or None
    stamp = Stamp.objects.create(
        id=stamp_id or uuid.uuid4(), visit=visit, user=user, place_id=visit.place_id, **data
    )
    set_stamp_media(stamp, user, links)
    return stamp, True


# --- Visitas ----------------------------------------------------------------


@router.get("/places/{place_id}/visits", response=list[VisitOut])
def list_place_visits(request, place_id: uuid.UUID):
    place = visible_place(request.user, place_id)
    return [visit_out(v) for v in visit_queryset(request.user).filter(place=place)]


@router.post("/places/{place_id}/visits", response={200: VisitOut, 201: VisitOut, 409: ErrorOut})
def create_visit(request, place_id: uuid.UUID, payload: VisitIn):
    user = request.user
    data = payload.dict()
    visit_id = data.pop("id", None)
    media_ids = data.pop("media")
    stamps = data.pop("stamps")
    if visit_id:
        existing = Visit.objects.filter(id=visit_id).first()
        if existing:
            if existing.user_id != user.id or existing.place_id != place_id:
                return Status(409, {"detail": "id_conflict"})
            return Status(200, visit_out(visit_queryset(user).get(id=existing.id)))
    place = visible_place(user, place_id)
    if place.status == "merged":
        return Status(409, {"detail": "place_merged"})
    visit = Visit(id=visit_id or uuid.uuid4(), user=user, place=place)
    apply_visit_fields(visit, data)
    with transaction.atomic():
        visit.save(force_insert=True)
        set_visit_media(visit, user, media_ids)
        for stamp in stamps:
            create_stamp(user, visit, stamp)
    return Status(201, visit_out(visit_queryset(user).get(id=visit.id)))


@router.get("/visits", response=list[VisitWithPlace])
def recent_visits(request, limit: int = 10):
    qs = visit_queryset(request.user).order_by("-created_at")[: max(1, min(limit, 50))]
    return [visit_out(v, with_place=True) for v in qs]


@router.patch("/visits/{visit_id}", response=VisitOut)
def update_visit(request, visit_id: uuid.UUID, payload: VisitPatch):
    user = request.user
    visit = get_object_or_404(Visit, id=visit_id, user=user, deleted_at__isnull=True)
    data = payload.dict(exclude_unset=True)
    media_ids = data.pop("media", None)
    if "visited_precision" in data and data["visited_precision"] is None:
        del data["visited_precision"]
    if "kind" in data and data["kind"] is None:
        del data["kind"]
    apply_visit_fields(visit, data)
    with transaction.atomic():
        visit.save()
        if media_ids is not None:
            set_visit_media(visit, user, media_ids)
    return visit_out(visit_queryset(user).get(id=visit.id))


@router.delete("/visits/{visit_id}", response={204: None})
def delete_visit(request, visit_id: uuid.UUID):
    visit = get_object_or_404(Visit, id=visit_id, user=request.user, deleted_at__isnull=True)
    now = timezone.now()
    with transaction.atomic():
        Visit.objects.filter(id=visit.id).update(deleted_at=now)
        Stamp.objects.filter(visit_id=visit.id, deleted_at__isnull=True).update(deleted_at=now)
    return Status(204, None)


# --- Goshuin y sellos -------------------------------------------------------


@router.post("/visits/{visit_id}/stamps", response={200: StampOut, 201: StampOut, 409: ErrorOut})
def add_stamp(request, visit_id: uuid.UUID, payload: StampIn):
    user = request.user
    visit = get_object_or_404(Visit, id=visit_id, user=user, deleted_at__isnull=True)
    with transaction.atomic():
        stamp, created = create_stamp(user, visit, payload.dict())
    stamp = stamp_queryset(user).get(id=stamp.id) if stamp.deleted_at is None else stamp
    return Status(201 if created else 200, stamp_out(stamp))


@router.get("/stamps", response=StampPage)
def list_stamps(
    request,
    kind: Optional[StampKindLiteral] = None,
    prefecture: Optional[int] = None,
    region: Optional[int] = None,
    category: Optional[str] = None,
    year: Optional[int] = None,
    goshuincho: Optional[uuid.UUID] = None,
    place: Optional[uuid.UUID] = None,
    offset: int = 0,
    limit: int = 48,
):
    qs = stamp_queryset(request.user)
    if kind:
        qs = qs.filter(kind=kind)
    if prefecture:
        qs = qs.filter(place__prefecture_id=prefecture)
    if region:
        qs = qs.filter(place__prefecture__region_id=region)
    if category:
        qs = qs.filter(place__categories__slug=category).distinct()
    if year:
        qs = qs.filter(visit__visited_on__year=year)
    if goshuincho:
        qs = qs.filter(goshuincho_id=goshuincho)
    if place:
        qs = qs.filter(place_id=place)
    limit = max(1, min(limit, PAGE_MAX))
    offset = max(0, offset)
    count = qs.count()
    page = qs.order_by(F("visit__visited_on").desc(nulls_last=True), "-created_at")[offset : offset + limit]
    return {
        "items": [stamp_with_context(s) for s in page],
        "count": count,
        "next_offset": offset + limit if offset + limit < count else None,
    }


@router.patch("/stamps/{stamp_id}", response=StampOut)
def update_stamp(request, stamp_id: uuid.UUID, payload: StampPatch):
    user = request.user
    stamp = get_object_or_404(Stamp, id=stamp_id, user=user, deleted_at__isnull=True)
    data = payload.dict(exclude_unset=True)
    links = data.pop("media", None)
    if "goshuincho_id" in data:
        check_goshuincho(user, data["goshuincho_id"])
    if "kind" in data and data["kind"] is None:
        del data["kind"]
    for f, v in data.items():
        if f in ("title", "event_name", "page_label", "notes"):
            v = (v or "").strip() or None
        setattr(stamp, f, v)
    with transaction.atomic():
        stamp.save()
        if links is not None:
            set_stamp_media(stamp, user, links)
    return stamp_out(stamp_queryset(user).get(id=stamp.id))


@router.delete("/stamps/{stamp_id}", response={204: None})
def delete_stamp(request, stamp_id: uuid.UUID):
    stamp = get_object_or_404(Stamp, id=stamp_id, user=request.user, deleted_at__isnull=True)
    Stamp.objects.filter(id=stamp.id).update(deleted_at=timezone.now())
    return Status(204, None)


# --- Libretas ---------------------------------------------------------------


def goshuincho_out(item: Goshuincho, count: int) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "started_on": item.started_on,
        "finished_on": item.finished_on,
        "stamp_count": count,
    }


def goshuincho_list(user):
    return Goshuincho.objects.filter(user=user).annotate(
        n=Count("stamps", filter=Q(stamps__deleted_at__isnull=True))
    )


@router.get("/goshuincho", response=list[GoshuinchoOut])
def list_goshuincho(request):
    qs = goshuincho_list(request.user).order_by(F("started_on").desc(nulls_last=True), "name")
    return [goshuincho_out(g, g.n) for g in qs]


@router.post("/goshuincho", response={200: GoshuinchoOut, 201: GoshuinchoOut, 409: ErrorOut})
def create_goshuincho(request, payload: GoshuinchoIn):
    user = request.user
    data = payload.dict()
    item_id = data.pop("id", None)
    if item_id:
        existing = goshuincho_list(user).filter(id=item_id).first()
        if existing:
            return Status(200, goshuincho_out(existing, existing.n))
        if Goshuincho.objects.filter(id=item_id).exists():
            return Status(409, {"detail": "id_conflict"})
    data["name"] = data["name"].strip()
    item = Goshuincho.objects.create(id=item_id or uuid.uuid4(), user=user, **data)
    return Status(201, goshuincho_out(item, 0))


@router.patch("/goshuincho/{item_id}", response=GoshuinchoOut)
def update_goshuincho(request, item_id: uuid.UUID, payload: GoshuinchoPatch):
    item = get_object_or_404(Goshuincho, id=item_id, user=request.user)
    for f, v in payload.dict(exclude_unset=True).items():
        if f == "name":
            if not v or not v.strip():
                continue
            v = v.strip()
        setattr(item, f, v)
    item.save()
    item = goshuincho_list(request.user).get(id=item.id)
    return goshuincho_out(item, item.n)


@router.delete("/goshuincho/{item_id}", response={204: None})
def delete_goshuincho(request, item_id: uuid.UUID):
    get_object_or_404(Goshuincho, id=item_id, user=request.user).delete()
    return Status(204, None)


# --- Imágenes ---------------------------------------------------------------


@router.post("/media", response={200: MediaOut, 201: MediaOut, 413: ErrorOut, 415: ErrorOut})
def upload_media(request, file: File[UploadedFile], id: Form[Optional[uuid.UUID]] = None):
    from django.conf import settings

    from .tasks import make_variants

    user = request.user
    if id:
        existing = Media.objects.filter(id=id, user=user).first()
        if existing:
            return Status(200, media_out(existing))
    try:
        tmp, sha, size = storage.save_upload(file)
    except storage.TooLarge:
        return Status(413, {"detail": "file_too_large"})
    try:
        existing = Media.objects.filter(user=user, sha256=sha).first()
        if existing:
            return Status(200, media_out(existing))
        try:
            info = storage.inspect(tmp)
        except storage.InvalidImage:
            return Status(415, {"detail": "unsupported_image"})
        if not settings.KEEP_ORIGINAL_EXIF:
            storage.strip_location(tmp)
            size = tmp.stat().st_size
        key = storage.storage_key(user.id, sha, info["ext"])
        storage.store(tmp, key)
        try:
            item = Media.objects.create(
                id=id or uuid.uuid4(),
                user=user,
                sha256=sha,
                mime=info["mime"],
                bytes=size,
                width=info["width"],
                height=info["height"],
                taken_at=info["taken_at"],
                storage_key=key,
            )
        except IntegrityError:
            # Subida simultánea del mismo fichero: devuelve la que ganó.
            return Status(200, media_out(Media.objects.get(user=user, sha256=sha)))
    finally:
        if tmp.exists():
            tmp.unlink()
    try:
        make_variants.defer(media_id=str(item.id))
    except Exception:
        storage.ensure_variants(item)
    return Status(201, media_out(item))


@router.get("/media/{media_id}/{variant}")
def download_media(request, media_id: uuid.UUID, variant: Literal["thumb", "medium", "original"]):
    item = get_object_or_404(Media, id=media_id, user=request.user)
    if variant == "original":
        key, mime = item.storage_key, item.mime
    else:
        storage.ensure_variants(item)
        key, mime = item.variants[variant], "image/webp"
    path = storage.media_root() / key
    if not path.exists():
        raise HttpError(404, "Not Found")
    response = FileResponse(open(path, "rb"), content_type=mime)
    response["Cache-Control"] = "private, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# --- Estadísticas -----------------------------------------------------------


@router.get("/stats/summary", response=StatsOut)
def stats_summary(request):
    user = request.user
    summary = UserPlaceSummary.objects.filter(user=user)
    visited = summary.filter(visit_count__gt=0)
    stamps = stamp_queryset(user)
    by_prefecture = (
        visited.values("place__prefecture_id").annotate(n=Count("place_id")).order_by("-n")
    )
    by_kind = stamps.values("kind").annotate(n=Count("id")).order_by("-n")
    by_year = (
        Visit.objects.filter(user=user, deleted_at__isnull=True, visited_on__isnull=False, kind=VisitKind.IN_PERSON)
        .annotate(y=ExtractYear("visited_on"))
        .values("y")
        .annotate(n=Count("id"))
        .order_by("-y")
    )
    return {
        "places_visited": visited.count(),
        "visits": Visit.objects.filter(user=user, deleted_at__isnull=True, kind=VisitKind.IN_PERSON).count(),
        "stamps": stamps.count(),
        "goshuin": stamps.filter(kind__startswith="goshuin").count(),
        "prefectures_visited": by_prefecture.count(),
        "by_prefecture": [{"key": str(r["place__prefecture_id"]), "count": r["n"]} for r in by_prefecture],
        "by_kind": [{"key": r["kind"], "count": r["n"]} for r in by_kind],
        "by_year": [{"key": str(r["y"]), "count": r["n"]} for r in by_year],
    }


def month_streaks(months: set[tuple[int, int]], today: date) -> tuple[int, int]:
    """Rachas de meses consecutivos con alguna visita. La actual sigue viva si el último mes es este o el anterior."""
    index = sorted(y * 12 + m - 1 for y, m in months)
    longest = run = 0
    prev = None
    for i in index:
        run = run + 1 if prev is not None and i == prev + 1 else 1
        longest = max(longest, run)
        prev = i
    now = today.year * 12 + today.month - 1
    current = run if index and index[-1] >= now - 1 else 0
    return longest, current


@router.get("/stats/detail", response=StatsDetailOut)
def stats_detail(request, year: Optional[int] = None):
    user = request.user
    visits = Visit.objects.filter(user=user, deleted_at__isnull=True, kind=VisitKind.IN_PERSON)
    visited = UserPlaceSummary.objects.filter(user=user, visit_count__gt=0)
    goshuin = stamp_queryset(user).filter(kind__startswith="goshuin")
    approved = Place.objects.filter(status=ReviewStatus.APPROVED)

    available = dict(approved.values_list("prefecture_id").annotate(n=Count("id")))
    mine = dict(visited.values_list("place__prefecture_id").annotate(n=Count("place_id")))
    stamped = dict(goshuin.values_list("place__prefecture_id").annotate(n=Count("id")))
    by_prefecture = [
        {"id": pid, "places": available.get(pid, 0), "visited": mine.get(pid, 0), "goshuin": stamped.get(pid, 0)}
        for pid in sorted(set(available) | set(mine) | set(stamped))
    ]
    region_places = dict(approved.values_list("prefecture__region_id").annotate(n=Count("id")))
    region_visited = dict(visited.values_list("place__prefecture__region_id").annotate(n=Count("place_id")))
    by_region = [
        {"id": rid, "places": region_places.get(rid, 0), "visited": region_visited.get(rid, 0)}
        for rid in sorted(set(region_places) | set(region_visited))
    ]
    by_place_kind = visited.values("place__kind").annotate(n=Count("place_id")).order_by("-n")
    goshuin_by_year = (
        goshuin.filter(visit__visited_on__isnull=False)
        .annotate(y=ExtractYear("visit__visited_on"))
        .values("y")
        .annotate(n=Count("id"))
        .order_by("y")
    )

    dated = visits.filter(visited_on__isnull=False)
    precise = dated.filter(visited_precision__in=[DatePrecision.DAY, DatePrecision.MONTH])
    months = {(d.year, d.month) for d in precise.annotate(m=TruncMonth("visited_on")).values_list("m", flat=True)}
    longest, current = month_streaks(months, timezone.localdate())

    years = sorted({d.year for d in dated.values_list("visited_on", flat=True)}, reverse=True)
    heatmap_year = year or timezone.localdate().year
    days = (
        visits.filter(visited_precision=DatePrecision.DAY, visited_on__year=heatmap_year)
        .values("visited_on")
        .annotate(n=Count("id"))
        .order_by("visited_on")
    )
    return {
        "by_prefecture": by_prefecture,
        "by_region": by_region,
        "by_place_kind": [{"key": r["place__kind"], "count": r["n"]} for r in by_place_kind],
        "goshuin_by_year": [{"key": str(r["y"]), "count": r["n"]} for r in goshuin_by_year],
        "longest_streak_months": longest,
        "current_streak_months": current,
        "heatmap_year": heatmap_year,
        "heatmap": [{"date": r["visited_on"], "count": r["n"]} for r in days],
        "years": years,
    }


# --- Copia personal -----------------------------------------------------------


class ImportOut(Schema):
    places_created: int
    places_matched: int
    visits: int
    stamps: int
    media: int
    goshuincho: int


@router.post("/export")
def export_collection(request):
    from . import portability

    path = portability.build_export_zip(request.user)
    handle = open(path, "rb")
    path.unlink()
    stamp = timezone.localdate().isoformat()
    return FileResponse(
        handle,
        as_attachment=True,
        filename=f"goshuincho-{stamp}.zip",
        content_type="application/zip",
    )


@router.post("/import", response={200: ImportOut, 400: ErrorOut})
def import_collection(request, file: File[UploadedFile]):
    from . import portability

    try:
        stats = portability.import_archive(request.user, file)
    except portability.ImportError_ as exc:
        return Status(400, {"detail": str(exc)})
    return Status(200, stats)
