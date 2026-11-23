import uuid
from datetime import date, datetime
from typing import Literal, Optional

from django.contrib.gis.geos import Point, Polygon
from django.db.models import BooleanField, Exists, F, OuterRef, Q
from django.db.models.expressions import RawSQL
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from geo.models import Area, Prefecture
from geo.utils import prefecture_for_point
from visits.models import UserPlaceSummary, Visit, VisitKind

from .models import Category, Place, PlaceCategory, PlaceCorrection, PlaceKind, PlaceSource, ReviewStatus, UserPlace

router = Router(tags=["places"])

NAME_EXPR = "(coalesce(places.name_ja,'') || ' ' || coalesce(places.name_romaji,'') || ' ' || coalesce(places.name_en,''))"
# Romaji sin macrones, guiones ni espacios: «toji» encuentra «Tō-ji».
FOLDED_EXPR = (
    "regexp_replace(lower(translate(coalesce(places.name_romaji,'') || ' ' || coalesce(places.name_en,'') || ' ' "
    "|| array_to_string(places.alt_names, ' '), 'āīūēōĀĪŪĒŌâîûêô', 'aiueoaiueoaiueo')), '[^[:alnum:]]', '', 'g')"
)
MACRONS = str.maketrans("āīūēōâîûêô", "aiueoaiueo")
MAX_UNVISITED_BBOX_DEG2 = 4.0
PAGE_MAX = 100
MAP_MAX = 4000


def fold(text: str) -> str:
    return "".join(ch for ch in text.lower().translate(MACRONS) if ch.isalnum())


def like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def searchable_places(user):
    """Lugares que aparecen en búsquedas: aprobados y los pendientes propios."""
    return Place.objects.filter(
        Q(status=ReviewStatus.APPROVED) | Q(status=ReviewStatus.PENDING, created_by=user)
    )


def visible_place(user, place_id) -> Place:
    place = get_object_or_404(Place.objects.select_related("prefecture__region", "area"), id=place_id)
    if place.status in (ReviewStatus.APPROVED, ReviewStatus.MERGED):
        return place
    if place.status == ReviewStatus.PENDING and place.created_by_id == user.id:
        return place
    if place.status == ReviewStatus.REJECTED and place.visits.filter(user=user).exists():
        return place
    raise HttpError(404, "Not Found")


def editable_place(user, place_id) -> Place:
    place = get_object_or_404(Place, id=place_id)
    if place.status != ReviewStatus.PENDING or place.created_by_id != user.id:
        raise HttpError(403, "not_editable")
    return place


# --- Esquemas ---------------------------------------------------------------


class MineSummary(Schema):
    visit_count: int = 0
    last_visit: Optional[date] = None
    last_visit_precision: Optional[str] = None
    stamp_count: int = 0
    wishlist: bool = False
    favorite: bool = False


class PlaceListItem(Schema):
    id: uuid.UUID
    kind: str
    name_ja: Optional[str]
    name_romaji: Optional[str]
    name_en: Optional[str]
    prefecture_id: int
    area_id: Optional[int]
    lat: Optional[float]
    lon: Optional[float]
    status: str
    mine: MineSummary


class PlacePage(Schema):
    items: list[PlaceListItem]
    count: int
    next_offset: Optional[int]


class PrefectureRef(Schema):
    id: int
    name_ja: str
    name_en: str
    name_es: str
    region: str


class AreaRef(Schema):
    id: int
    name_ja: Optional[str]
    name_en: str
    name_es: Optional[str]


class CategoryRef(Schema):
    slug: str
    type: str
    name_ja: Optional[str]
    name_en: str
    name_es: Optional[str]
    seq: Optional[int]


class MineDetail(MineSummary):
    first_visit: Optional[date] = None
    first_visit_precision: Optional[str] = None
    notes: Optional[str] = None


class PlaceDetail(Schema):
    id: uuid.UUID
    kind: str
    name_ja: Optional[str]
    name_romaji: Optional[str]
    name_en: Optional[str]
    name_romaji_generated: bool
    alt_names: list[str]
    tradition: Optional[str]
    operator: Optional[str]
    prefecture: PrefectureRef
    area: Optional[AreaRef]
    address: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    website: Optional[str]
    goshuin_available: Optional[bool]
    goshuin_info: Optional[str]
    source: str
    status: str
    merged_into: Optional[uuid.UUID]
    is_mine: bool
    categories: list[CategoryRef]
    mine: MineDetail


class PlaceIn(Schema):
    id: Optional[uuid.UUID] = None
    kind: Literal["shrine", "temple", "station", "site"]
    name_ja: Optional[str] = Field(None, max_length=200)
    name_romaji: Optional[str] = Field(None, max_length=200)
    name_en: Optional[str] = Field(None, max_length=200)
    lat: Optional[float] = Field(None, ge=20, le=46)
    lon: Optional[float] = Field(None, ge=122, le=154)
    prefecture_id: Optional[int] = None
    area_id: Optional[int] = None
    address: Optional[str] = None
    tradition: Optional[str] = None
    operator: Optional[str] = None
    website: Optional[str] = None
    goshuin_available: Optional[bool] = None
    goshuin_info: Optional[str] = None


class PlacePatch(Schema):
    kind: Optional[Literal["shrine", "temple", "station", "site"]] = None
    name_ja: Optional[str] = Field(None, max_length=200)
    name_romaji: Optional[str] = Field(None, max_length=200)
    name_en: Optional[str] = Field(None, max_length=200)
    lat: Optional[float] = Field(None, ge=20, le=46)
    lon: Optional[float] = Field(None, ge=122, le=154)
    prefecture_id: Optional[int] = None
    area_id: Optional[int] = None
    address: Optional[str] = None
    tradition: Optional[str] = None
    operator: Optional[str] = None
    website: Optional[str] = None
    goshuin_available: Optional[bool] = None
    goshuin_info: Optional[str] = None


class MineIn(Schema):
    wishlist: bool = False
    favorite: bool = False
    notes: Optional[str] = None


class SimilarItem(Schema):
    id: uuid.UUID
    kind: str
    name_ja: Optional[str]
    name_romaji: Optional[str]
    name_en: Optional[str]
    prefecture_id: int
    distance_m: Optional[float]


class CategoryOut(Schema):
    id: int
    slug: str
    type: str
    name_ja: Optional[str]
    name_en: str
    name_es: Optional[str]
    total_items: Optional[int]


class MapPoint(Schema):
    id: uuid.UUID
    kind: str
    lon: float
    lat: float
    state: Literal["visited", "wishlist", "unvisited"]
    name_ja: Optional[str]
    name_romaji: Optional[str]
    name_en: Optional[str]


class MapPoints(Schema):
    items: list[MapPoint]
    truncated: bool


class ErrorOut(Schema):
    detail: str


# --- Utilidades -------------------------------------------------------------


def mine_summaries(user, place_ids) -> dict:
    result = {pid: {} for pid in place_ids}
    for s in UserPlaceSummary.objects.filter(user=user, place_id__in=place_ids):
        result[s.place_id].update(
            visit_count=s.visit_count,
            last_visit=s.last_visit,
            last_visit_precision=s.last_visit_precision,
            stamp_count=s.stamp_count,
        )
    for up in UserPlace.objects.filter(user=user, place_id__in=place_ids):
        result[up.place_id].update(wishlist=up.wishlist, favorite=up.favorite, notes=up.notes)
    return result


def list_item(place: Place, mine: dict) -> dict:
    return {
        "id": place.id,
        "kind": place.kind,
        "name_ja": place.name_ja,
        "name_romaji": place.name_romaji,
        "name_en": place.name_en,
        "prefecture_id": place.prefecture_id,
        "area_id": place.area_id,
        "lat": place.location.y if place.location else None,
        "lon": place.location.x if place.location else None,
        "status": place.status,
        "mine": mine,
    }


def place_detail(user, place: Place) -> dict:
    mine = mine_summaries(user, [place.id])[place.id]
    first = (
        Visit.objects.filter(user=user, place=place, kind=VisitKind.IN_PERSON, deleted_at__isnull=True)
        .exclude(visited_on__isnull=True)
        .order_by("visited_on")
        .first()
    )
    if first:
        mine.update(first_visit=first.visited_on, first_visit_precision=first.visited_precision)
    categories = [
        {
            "slug": pc.category.slug,
            "type": pc.category.type,
            "name_ja": pc.category.name_ja,
            "name_en": pc.category.name_en,
            "name_es": pc.category.name_es,
            "seq": pc.seq,
        }
        for pc in place.placecategory_set.select_related("category").order_by("category__type", "category__slug")
    ]
    pref = place.prefecture
    return {
        **list_item(place, mine),
        "name_romaji_generated": place.name_romaji_generated,
        "alt_names": place.alt_names,
        "tradition": place.tradition,
        "operator": place.operator,
        "prefecture": {
            "id": pref.id,
            "name_ja": pref.name_ja,
            "name_en": pref.name_en,
            "name_es": pref.name_es,
            "region": pref.region.slug,
        },
        "area": place.area,
        "address": place.address,
        "website": place.website,
        "goshuin_available": place.goshuin_available,
        "goshuin_info": place.goshuin_info,
        "source": place.source,
        "merged_into": place.merged_into_id,
        "is_mine": place.created_by_id == user.id,
        "categories": categories,
    }


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        minlon, minlat, maxlon, maxlat = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HttpError(422, "invalid_bbox")
    if minlon >= maxlon or minlat >= maxlat:
        raise HttpError(422, "invalid_bbox")
    return minlon, minlat, maxlon, maxlat


def apply_location(place: Place, data: dict):
    lat, lon = data.pop("lat", None), data.pop("lon", None)
    if (lat is None) != (lon is None):
        raise HttpError(422, "lat_lon_together")
    if lat is not None:
        place.location = Point(lon, lat, srid=4326)
    prefecture_id = data.pop("prefecture_id", None)
    if prefecture_id is not None:
        if not Prefecture.objects.filter(id=prefecture_id).exists():
            raise HttpError(422, "invalid_prefecture")
        place.prefecture_id = prefecture_id
    elif lat is not None:
        place.prefecture = prefecture_for_point(lon, lat) or place.prefecture
    area_id = data.pop("area_id", None)
    if area_id is not None:
        place.area_id = area_id
    if place.area_id and not Area.objects.filter(id=place.area_id, prefecture_id=place.prefecture_id).exists():
        raise HttpError(422, "invalid_area")


def clean_names(place: Place):
    for f in ("name_ja", "name_romaji", "name_en"):
        value = getattr(place, f)
        setattr(place, f, value.strip() or None if value else None)
    if not (place.name_ja or place.name_romaji or place.name_en):
        raise HttpError(422, "name_required")


# --- Endpoints --------------------------------------------------------------


@router.get("/categories", response=list[CategoryOut])
def categories(request):
    return Category.objects.all()


class CategoryProgress(CategoryOut):
    description: Optional[str]
    members: int
    total: int
    done: int
    visited: int
    stamped: int


class CategoryMember(PlaceListItem):
    seq: Optional[int]


class CategoryDetailOut(CategoryProgress):
    places: list[CategoryMember]


def category_progress(user, categories) -> list[dict]:
    """Progreso por categoría: un lugar cuenta como hecho con visita en persona o goshuin."""
    ids = [c.id for c in categories]
    links = PlaceCategory.objects.filter(category_id__in=ids, place__in=searchable_places(user))
    members: dict[int, set] = {i: set() for i in ids}
    for cat_id, place_id in links.values_list("category_id", "place_id"):
        members[cat_id].add(place_id)
    all_places = set().union(*members.values()) if members else set()
    summaries = {
        s.place_id: s for s in UserPlaceSummary.objects.filter(user=user, place_id__in=all_places)
    }
    out = []
    for c in categories:
        places = members[c.id]
        visited = sum(1 for p in places if p in summaries and summaries[p].visit_count)
        stamped = sum(1 for p in places if p in summaries and summaries[p].stamp_count)
        done = sum(1 for p in places if p in summaries)
        out.append(
            {
                "id": c.id,
                "slug": c.slug,
                "type": c.type,
                "name_ja": c.name_ja,
                "name_en": c.name_en,
                "name_es": c.name_es,
                "description": c.description,
                "total_items": c.total_items,
                "members": len(places),
                "total": max(c.total_items or 0, len(places)),
                "done": done,
                "visited": visited,
                "stamped": stamped,
            }
        )
    return out


@router.get("/categories/progress", response=list[CategoryProgress])
def categories_progress(request, type: Optional[str] = None):
    qs = Category.objects.all()
    if type:
        qs = qs.filter(type=type)
    return category_progress(request.user, list(qs))


@router.get("/categories/{slug}", response=CategoryDetailOut)
def category_detail(request, slug: str):
    user = request.user
    category = get_object_or_404(Category, slug=slug)
    data = category_progress(user, [category])[0]
    links = (
        PlaceCategory.objects.filter(category=category, place__in=searchable_places(user))
        .select_related("place")
        .order_by(F("seq").asc(nulls_last=True), "place__name_romaji", "place__name_ja")
    )
    links = list(links)
    mine = mine_summaries(user, [link.place_id for link in links])
    data["places"] = [{**list_item(link.place, mine[link.place_id]), "seq": link.seq} for link in links]
    return data


@router.get("/places", response=PlacePage)
def list_places(
    request,
    q: Optional[str] = None,
    kind: Optional[Literal["shrine", "temple", "station", "site"]] = None,
    category: Optional[str] = None,
    region: Optional[int] = None,
    prefecture: Optional[int] = None,
    area: Optional[int] = None,
    state: Optional[Literal["visited", "wishlist", "unvisited", "favorite"]] = None,
    bbox: Optional[str] = None,
    offset: int = 0,
    limit: int = 30,
):
    user = request.user
    limit = max(1, min(limit, PAGE_MAX))
    offset = max(0, offset)
    qs = searchable_places(user)
    if kind:
        qs = qs.filter(kind=kind)
    if category:
        qs = qs.filter(categories__slug=category)
    if region:
        qs = qs.filter(prefecture__region_id=region)
    if prefecture:
        qs = qs.filter(prefecture_id=prefecture)
    if area:
        qs = qs.filter(area_id=area)
    if bbox:
        minlon, minlat, maxlon, maxlat = parse_bbox(bbox)
        qs = qs.filter(location__intersects=Polygon.from_bbox((minlon, minlat, maxlon, maxlat)))
    visited = Exists(
        Visit.objects.filter(
            user=user, place=OuterRef("pk"), kind=VisitKind.IN_PERSON, deleted_at__isnull=True
        )
    )
    if state == "visited":
        qs = qs.filter(visited)
    elif state == "unvisited":
        if not bbox or (maxlon - minlon) * (maxlat - minlat) > MAX_UNVISITED_BBOX_DEG2:
            raise HttpError(422, "bbox_required")
        qs = qs.filter(~visited)
    elif state in ("wishlist", "favorite"):
        qs = qs.filter(Exists(UserPlace.objects.filter(user=user, place=OuterRef("pk"), **{state: True})))

    order = ["name_romaji", "name_en", "name_ja", "id"]
    q = (q or "").strip()
    if q:
        pattern = f"%{like_escape(q)}%"
        folded = fold(q)
        cond = f"{NAME_EXPR} ILIKE %s"
        params = [pattern]
        if folded:
            cond += f" OR {FOLDED_EXPR} LIKE %s"
            params.append(f"%{folded}%")
        cond += " OR array_to_string(places.alt_names, ' ') ILIKE %s"
        params.append(pattern)
        qs = qs.filter(RawSQL(f"({cond})", params, output_field=BooleanField()))
        qs = qs.annotate(rank=RawSQL(f"similarity({NAME_EXPR}, %s)", [q]))
        order = ["-rank", *order]

    qs = qs.distinct() if category else qs
    count = qs.count()
    page = list(qs.order_by(*order)[offset : offset + limit])
    mine = mine_summaries(user, [p.id for p in page])
    next_offset = offset + limit if offset + limit < count else None
    return {"items": [list_item(p, mine[p.id]) for p in page], "count": count, "next_offset": next_offset}


@router.get("/places/map", response=MapPoints)
def map_points(
    request,
    bbox: Optional[str] = None,
    kind: Optional[Literal["shrine", "temple", "station", "site"]] = None,
    category: Optional[str] = None,
):
    """Puntos del mapa: siempre los visitados y en lista de deseos; con `bbox`, también el resto de esa zona."""
    user = request.user
    visited = Exists(
        Visit.objects.filter(user=user, place=OuterRef("pk"), kind=VisitKind.IN_PERSON, deleted_at__isnull=True)
    )
    wished = Exists(UserPlace.objects.filter(user=user, place=OuterRef("pk"), wishlist=True))
    qs = searchable_places(user).filter(location__isnull=False)
    if kind:
        qs = qs.filter(kind=kind)
    if category:
        qs = qs.filter(Exists(PlaceCategory.objects.filter(place=OuterRef("pk"), category__slug=category)))
    qs = qs.annotate(visited=visited, wished=wished)
    cond = Q(visited=True) | Q(wished=True)
    if bbox:
        minlon, minlat, maxlon, maxlat = parse_bbox(bbox)
        if (maxlon - minlon) * (maxlat - minlat) <= MAX_UNVISITED_BBOX_DEG2:
            cond |= Q(location__intersects=Polygon.from_bbox((minlon, minlat, maxlon, maxlat)))
    rows = list(
        qs.filter(cond)
        .order_by("-visited", "-wished", "id")
        .values_list("id", "kind", "location", "visited", "wished", "name_ja", "name_romaji", "name_en")[
            : MAP_MAX + 1
        ]
    )
    items = [
        {
            "id": pid,
            "kind": k,
            "lon": round(loc.x, 6),
            "lat": round(loc.y, 6),
            "state": "visited" if v else "wishlist" if w else "unvisited",
            "name_ja": ja,
            "name_romaji": ro,
            "name_en": en,
        }
        for pid, k, loc, v, w, ja, ro, en in rows[:MAP_MAX]
    ]
    return {"items": items, "truncated": len(rows) > MAP_MAX}


def similar_queryset(qs, name: str, lat: Optional[float] = None, lon: Optional[float] = None):
    """Posibles duplicados: nombre parecido cerca del punto, o cualquier lugar a menos de 150 m."""
    from django.contrib.gis.db.models.functions import Distance
    from django.contrib.gis.measure import D

    name = name.strip()
    name_match = RawSQL(
        f"(similarity({NAME_EXPR}, %s) > 0.3 OR {FOLDED_EXPR} LIKE %s)",
        [name, f"%{fold(name)}%" if fold(name) else "\x00"],
        output_field=BooleanField(),
    )
    if lat is not None and lon is not None:
        point = Point(lon, lat, srid=4326)
        qs = qs.filter(location__dwithin=(point, D(km=3))).annotate(distance=Distance("location", point))
        return qs.filter(Q(name_match) | Q(distance__lte=150)).order_by("distance")
    return qs.filter(name_match).annotate(rank=RawSQL(f"similarity({NAME_EXPR}, %s)", [name])).order_by("-rank")


@router.get("/places/similar", response=list[SimilarItem])
def similar_places(request, name: str, lat: Optional[float] = None, lon: Optional[float] = None):
    qs = similar_queryset(searchable_places(request.user), name, lat, lon)
    return [
        {
            "id": p.id,
            "kind": p.kind,
            "name_ja": p.name_ja,
            "name_romaji": p.name_romaji,
            "name_en": p.name_en,
            "prefecture_id": p.prefecture_id,
            "distance_m": round(p.distance.m, 1) if getattr(p, "distance", None) is not None else None,
        }
        for p in qs[:5]
    ]


@router.get("/places/{place_id}", response=PlaceDetail)
def get_place(request, place_id: uuid.UUID):
    return place_detail(request.user, visible_place(request.user, place_id))


@router.post("/places", response={200: PlaceDetail, 201: PlaceDetail, 409: ErrorOut})
def create_place(request, payload: PlaceIn):
    user = request.user
    data = payload.dict()
    place_id = data.pop("id", None)
    if place_id:
        existing = Place.objects.filter(id=place_id).first()
        if existing:
            if existing.created_by_id != user.id:
                return Status(409, {"detail": "id_conflict"})
            return Status(200, place_detail(user, visible_place(user, existing.id)))
    if data.get("lat") is None and data.get("prefecture_id") is None:
        raise HttpError(422, "location_or_prefecture_required")
    place = Place(
        id=place_id or uuid.uuid4(),
        source=PlaceSource.USER,
        status=ReviewStatus.PENDING,
        created_by=user,
    )
    apply_location(place, data)
    for f, v in data.items():
        setattr(place, f, v)
    clean_names(place)
    place.save()
    return Status(201, place_detail(user, visible_place(user, place.id)))


@router.patch("/places/{place_id}", response=PlaceDetail)
def update_place(request, place_id: uuid.UUID, payload: PlacePatch):
    place = editable_place(request.user, place_id)
    apply_patch(place, payload.dict(exclude_unset=True))
    place.save()
    return place_detail(request.user, visible_place(request.user, place.id))


def apply_patch(place: Place, data: dict):
    """Aplica campos con el formato de PlacePatch (sin guardar)."""
    data = dict(data)
    apply_location(place, data)
    for f, v in data.items():
        if f == "kind" and v is None:
            continue
        setattr(place, f, v)
    clean_names(place)


# --- Propuestas de corrección ----------------------------------------------

MAX_PENDING_CORRECTIONS = 20


class CorrectionIn(Schema):
    changes: PlacePatch
    comment: Optional[str] = Field(None, max_length=2000)


class CorrectionOut(Schema):
    id: uuid.UUID
    changes: dict
    comment: str
    status: str
    created_at: datetime


def correction_diff(place: Place, changes: dict) -> dict:
    """Quita lo que no cambia respecto al lugar actual."""
    diff = {}
    if changes.get("lat") is not None and changes.get("lon") is not None:
        if place.location is None or (
            round(place.location.y, 6), round(place.location.x, 6)
        ) != (round(changes["lat"], 6), round(changes["lon"], 6)):
            diff["lat"], diff["lon"] = changes["lat"], changes["lon"]
    for f, v in changes.items():
        if f in ("lat", "lon"):
            continue
        if f == "kind" and v is None:
            continue
        if isinstance(v, str):
            v = v.strip() or None
        if v != getattr(place, f, None):
            diff[f] = v
    return diff


@router.post("/places/{place_id}/corrections", response={201: CorrectionOut, 409: ErrorOut, 422: ErrorOut, 429: ErrorOut})
def propose_correction(request, place_id: uuid.UUID, payload: CorrectionIn):
    place = visible_place(request.user, place_id)
    if place.status != ReviewStatus.APPROVED:
        # Los lugares propios pendientes se editan directamente con PATCH.
        return Status(409, {"detail": "not_approved"})
    changes = correction_diff(place, payload.changes.dict(exclude_unset=True))
    comment = (payload.comment or "").strip()
    if not changes and not comment:
        return Status(422, {"detail": "no_changes"})
    # Valida coordenadas, prefectura y zona sin guardar el lugar.
    apply_patch(Place.objects.get(pk=place.pk), changes)
    pending = PlaceCorrection.objects.filter(user=request.user, status=PlaceCorrection.Status.PENDING)
    if pending.count() >= MAX_PENDING_CORRECTIONS:
        return Status(429, {"detail": "too_many_pending"})
    item = PlaceCorrection.objects.create(place=place, user=request.user, changes=changes, comment=comment)
    return Status(201, item)


@router.get("/places/{place_id}/corrections", response=list[CorrectionOut])
def my_corrections(request, place_id: uuid.UUID):
    place = visible_place(request.user, place_id)
    return list(PlaceCorrection.objects.filter(place=place, user=request.user)[:20])


@router.delete("/places/{place_id}", response={204: None, 409: ErrorOut})
def delete_place(request, place_id: uuid.UUID):
    place = editable_place(request.user, place_id)
    if place.visits.exists():
        return Status(409, {"detail": "place_has_visits"})
    place.delete()
    return Status(204, None)


@router.put("/places/{place_id}/mine", response=MineDetail)
def set_mine(request, place_id: uuid.UUID, payload: MineIn):
    place = visible_place(request.user, place_id)
    notes = (payload.notes or "").strip() or None
    UserPlace.objects.update_or_create(
        user=request.user,
        place=place,
        defaults={"wishlist": payload.wishlist, "favorite": payload.favorite, "notes": notes},
    )
    return place_detail(request.user, place)["mine"]


__all__ = ["router", "PlaceKind"]
