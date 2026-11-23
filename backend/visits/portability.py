"""Copia personal: exporta la colección de un usuario a un ZIP y la restaura en otra instancia.

El ZIP contiene `data.json` y las imágenes originales en `media/`. La importación es idempotente:
los identificadores se conservan y lo que ya existe se omite, así que puede repetirse sin duplicar.
"""

import hashlib
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from geo.models import Area, Prefecture
from places.models import Place, PlaceSource, ReviewStatus, UserPlace

from . import media as storage
from .models import Goshuincho, Media, Stamp, StampMedia, Visit, VisitMedia

FORMAT = "goshuincho-export"
VERSION = 1
PLACE_FIELDS = (
    "kind", "name_ja", "name_romaji", "name_en", "alt_names", "tradition", "operator",
    "address", "website", "goshuin_available", "goshuin_info", "osm_type", "osm_id",
)
VISIT_FIELDS = ("kind", "event_location", "visited_on", "visited_precision", "notes", "created_at")
STAMP_FIELDS = ("kind", "medium", "title", "inscription", "event_name", "donation_yen", "page_label", "notes", "created_at")
MATCH_RADIUS_M = 300


class ImportError_(Exception):
    """Archivo de importación no válido."""


def _iso(value):
    return value.isoformat() if value else None


def _uuid(value) -> uuid.UUID:
    return uuid.UUID(str(value))


# --- Exportación --------------------------------------------------------------


def export_data(user) -> dict:
    visits = list(Visit.objects.filter(user=user, deleted_at__isnull=True).order_by("created_at"))
    visit_ids = {v.id for v in visits}
    stamps = list(
        Stamp.objects.filter(user=user, deleted_at__isnull=True, visit_id__in=visit_ids).order_by("created_at")
    )
    user_places = list(UserPlace.objects.filter(user=user))
    place_ids = {v.place_id for v in visits} | {up.place_id for up in user_places}
    own_pending = Place.objects.filter(created_by=user, status=ReviewStatus.PENDING).values_list("id", flat=True)
    place_ids |= set(own_pending)
    places = Place.objects.filter(id__in=place_ids).select_related("prefecture", "area")
    stamp_media = list(StampMedia.objects.filter(stamp__in=stamps))
    visit_media = list(VisitMedia.objects.filter(visit_id__in=visit_ids))
    media_ids = {m.media_id for m in stamp_media} | {m.media_id for m in visit_media}
    media = Media.objects.filter(user=user, id__in=media_ids)

    return {
        "format": FORMAT,
        "version": VERSION,
        "app_version": settings.VERSION,
        "exported_at": timezone.now().isoformat(),
        "user": {"email": user.email, "display_name": user.display_name, "locale": user.locale},
        "places": [
            {
                "id": str(p.id),
                **{f: getattr(p, f) for f in PLACE_FIELDS},
                "prefecture_id": p.prefecture_id,
                "area": p.area.slug if p.area_id else None,
                "location": [p.location.x, p.location.y] if p.location else None,
                "status": p.status,
                "own": p.created_by_id == user.id,
            }
            for p in places
        ],
        "user_places": [
            {"place_id": str(up.place_id), "wishlist": up.wishlist, "favorite": up.favorite, "notes": up.notes}
            for up in user_places
        ],
        "goshuincho": [
            {
                "id": str(g.id),
                "name": g.name,
                "description": g.description,
                "started_on": _iso(g.started_on),
                "finished_on": _iso(g.finished_on),
            }
            for g in Goshuincho.objects.filter(user=user)
        ],
        "visits": [
            {"id": str(v.id), "place_id": str(v.place_id), **{f: _iso_or(getattr(v, f)) for f in VISIT_FIELDS}}
            for v in visits
        ],
        "stamps": [
            {
                "id": str(s.id),
                "visit_id": str(s.visit_id),
                "goshuincho_id": str(s.goshuincho_id) if s.goshuincho_id else None,
                **{f: _iso_or(getattr(s, f)) for f in STAMP_FIELDS},
            }
            for s in stamps
        ],
        "media": [
            {
                "id": str(m.id),
                "sha256": m.sha256,
                "mime": m.mime,
                "taken_at": _iso(m.taken_at),
                "created_at": _iso(m.created_at),
                "file": _media_name(m),
            }
            for m in media
        ],
        "visit_media": [
            {"visit_id": str(m.visit_id), "media_id": str(m.media_id), "position": m.position}
            for m in visit_media
        ],
        "stamp_media": [
            {"stamp_id": str(m.stamp_id), "media_id": str(m.media_id), "role": m.role, "position": m.position}
            for m in stamp_media
        ],
    }


def _iso_or(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _media_name(item: Media) -> str:
    return f"media/{item.sha256}.{item.storage_key.rsplit('.', 1)[-1]}"


def build_export_zip(user) -> Path:
    """Escribe el ZIP en un temporal y devuelve su ruta; quien llama debe borrarlo."""
    data = export_data(user)
    fd, tmp = tempfile.mkstemp(prefix="goshuincho-export-", suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=1))
        for item in Media.objects.filter(id__in=[m["id"] for m in data["media"]]):
            src = storage.media_root() / item.storage_key
            if src.exists():
                # Las imágenes ya están comprimidas.
                zf.write(src, _media_name(item), compress_type=zipfile.ZIP_STORED)
    return Path(tmp)


# --- Importación --------------------------------------------------------------


def read_archive(path) -> tuple[zipfile.ZipFile, dict]:
    try:
        zf = zipfile.ZipFile(path)
        data = json.loads(zf.read("data.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ImportError_("invalid_archive") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ImportError_("invalid_archive")
    if data.get("version") != VERSION:
        raise ImportError_("unsupported_version")
    return zf, data


def import_archive(user, path) -> dict:
    zf, data = read_archive(path)
    with zf:
        try:
            return _Importer(user, zf, data).run()
        except (KeyError, TypeError, ValueError) as exc:
            raise ImportError_("invalid_archive") from exc


class _Importer:
    def __init__(self, user, zf: zipfile.ZipFile, data: dict):
        self.user = user
        self.zf = zf
        self.data = data
        self.stats = {key: 0 for key in ("places_created", "places_matched", "visits", "stamps", "media", "goshuincho")}
        self.place_map: dict[str, Place] = {}
        self.visit_map: dict[str, Visit] = {}
        self.stamp_map: dict[str, Stamp] = {}
        self.media_map: dict[str, Media] = {}
        self.book_map: dict[str, Goshuincho] = {}
        self.stored: list[Path] = []

    def run(self) -> dict:
        try:
            with transaction.atomic():
                for item in self.data.get("places", []):
                    self.place_map[item["id"]] = self.resolve_place(item)
                self.import_books()
                self.import_visits()
                self.import_stamps()
                self.import_user_places()
                self.import_media()
        except BaseException:
            for path in self.stored:
                path.unlink(missing_ok=True)
            raise
        for item in self.media_map.values():
            if not item.variants:
                try:
                    from .tasks import make_variants

                    make_variants.defer(media_id=str(item.id))
                except Exception:
                    storage.ensure_variants(item)
        return self.stats

    # Lugares: mismo id, misma referencia de OSM o mismo nombre cerca; si no, lugar privado nuevo.
    def resolve_place(self, item: dict) -> Place:
        place = Place.objects.filter(id=item["id"]).first()
        hops = 0
        while place and place.status == ReviewStatus.MERGED and place.merged_into_id and hops < 10:
            place = Place.objects.filter(id=place.merged_into_id).first()
            hops += 1
        if place and self.usable(place):
            self.stats["places_matched"] += 1
            return place
        if item.get("osm_id"):
            place = Place.objects.filter(osm_type=item.get("osm_type"), osm_id=item["osm_id"]).exclude(
                status=ReviewStatus.MERGED
            ).first()
            if place and self.usable(place):
                self.stats["places_matched"] += 1
                return place
        location = Point(*item["location"], srid=4326) if item.get("location") else None
        names = [n for n in (item.get("name_ja"), item.get("name_romaji"), item.get("name_en")) if n]
        if location and names:
            name_q = Q()
            for name in names:
                name_q |= Q(name_ja__iexact=name) | Q(name_romaji__iexact=name) | Q(name_en__iexact=name)
            place = (
                Place.objects.filter(name_q, kind=item["kind"], location__dwithin=(location, D(m=MATCH_RADIUS_M)))
                .filter(Q(status=ReviewStatus.APPROVED) | Q(status=ReviewStatus.PENDING, created_by=self.user))
                .first()
            )
            if place:
                self.stats["places_matched"] += 1
                return place
        return self.create_place(item, location)

    def usable(self, place: Place) -> bool:
        return place.status == ReviewStatus.APPROVED or (
            place.status in (ReviewStatus.PENDING, ReviewStatus.REJECTED) and place.created_by_id == self.user.id
        )

    def create_place(self, item: dict, location) -> Place:
        prefecture = Prefecture.objects.get(id=item["prefecture_id"])
        area = Area.objects.filter(prefecture=prefecture, slug=item["area"]).first() if item.get("area") else None
        fields = {f: item.get(f) for f in PLACE_FIELDS}
        fields["alt_names"] = fields["alt_names"] or []
        if fields["osm_id"] and Place.objects.filter(osm_type=fields["osm_type"], osm_id=fields["osm_id"]).exists():
            fields["osm_type"] = fields["osm_id"] = None
        place_id = _uuid(item["id"])
        if Place.objects.filter(id=place_id).exists():
            place_id = uuid.uuid5(place_id, str(self.user.id))
            existing = Place.objects.filter(id=place_id, created_by=self.user).first()
            if existing:
                self.stats["places_matched"] += 1
                return existing
        place = Place.objects.create(
            id=place_id,
            **fields,
            prefecture=prefecture,
            area=area,
            location=location,
            source=PlaceSource.MANUAL,
            status=ReviewStatus.PENDING,
            created_by=self.user,
        )
        self.stats["places_created"] += 1
        return place

    def free_id(self, model, raw) -> tuple[uuid.UUID, object]:
        """Devuelve el id a usar y el objeto propio que ya lo tiene (si lo hay)."""
        for value in (_uuid(raw), uuid.uuid5(_uuid(raw), str(self.user.id))):
            existing = model.objects.filter(id=value).first()
            if existing is None:
                return value, None
            if existing.user_id == self.user.id:
                return value, existing
        return uuid.uuid4(), None

    def import_books(self):
        for item in self.data.get("goshuincho", []):
            book_id, existing = self.free_id(Goshuincho, item["id"])
            if existing is None:
                existing = Goshuincho.objects.create(
                    id=book_id,
                    user=self.user,
                    name=item["name"],
                    description=item.get("description"),
                    started_on=parse_date(item["started_on"]) if item.get("started_on") else None,
                    finished_on=parse_date(item["finished_on"]) if item.get("finished_on") else None,
                )
                self.stats["goshuincho"] += 1
            self.book_map[item["id"]] = existing

    def import_visits(self):
        for item in self.data.get("visits", []):
            visit_id, existing = self.free_id(Visit, item["id"])
            if existing is None:
                existing = Visit(id=visit_id, user=self.user, place=self.place_map[item["place_id"]])
                for f in VISIT_FIELDS:
                    setattr(existing, f, item.get(f))
                existing.visited_on = parse_date(item["visited_on"]) if item.get("visited_on") else None
                existing.save()
                self.keep_created_at(Visit, existing, item)
                self.stats["visits"] += 1
            elif existing.deleted_at is not None:
                Visit.objects.filter(id=existing.id).update(deleted_at=None)
                self.stats["visits"] += 1
            self.visit_map[item["id"]] = existing

    def import_stamps(self):
        for item in self.data.get("stamps", []):
            stamp_id, existing = self.free_id(Stamp, item["id"])
            if existing is None:
                visit = self.visit_map[item["visit_id"]]
                existing = Stamp(id=stamp_id, user=self.user, visit=visit, place_id=visit.place_id)
                for f in STAMP_FIELDS:
                    setattr(existing, f, item.get(f))
                book = item.get("goshuincho_id")
                existing.goshuincho = self.book_map.get(book) if book else None
                existing.save()
                self.keep_created_at(Stamp, existing, item)
                self.stats["stamps"] += 1
            elif existing.deleted_at is not None:
                Stamp.objects.filter(id=existing.id).update(deleted_at=None)
                self.stats["stamps"] += 1
            self.stamp_map[item["id"]] = existing

    def keep_created_at(self, model, obj, item):
        created = parse_datetime(item["created_at"]) if item.get("created_at") else None
        if created:
            model.objects.filter(id=obj.id).update(created_at=created)

    def import_user_places(self):
        for item in self.data.get("user_places", []):
            place = self.place_map[item["place_id"]]
            row, created = UserPlace.objects.get_or_create(user=self.user, place=place)
            row.wishlist = row.wishlist or bool(item.get("wishlist"))
            row.favorite = row.favorite or bool(item.get("favorite"))
            note = item.get("notes")
            if note and note not in (row.notes or ""):
                row.notes = f"{row.notes}\n\n{note}" if row.notes else note
            row.save()

    def import_media(self):
        names = set(self.zf.namelist())
        limit = settings.MAX_UPLOAD_MB * 1024 * 1024
        for item in self.data.get("media", []):
            existing = Media.objects.filter(user=self.user, sha256=item["sha256"]).first()
            if existing is None:
                name = item.get("file")
                if name not in names or not name.startswith("media/"):
                    continue
                if self.zf.getinfo(name).file_size > limit:
                    continue
                existing = self.store_media(item, name)
                if existing is None:
                    continue
            self.media_map[item["id"]] = existing
        for link in self.data.get("visit_media", []):
            visit, item = self.visit_map.get(link["visit_id"]), self.media_map.get(link["media_id"])
            if visit and item:
                VisitMedia.objects.get_or_create(visit=visit, media=item, defaults={"position": link["position"]})
        for link in self.data.get("stamp_media", []):
            stamp, item = self.stamp_map.get(link["stamp_id"]), self.media_map.get(link["media_id"])
            if stamp and item:
                StampMedia.objects.get_or_create(
                    stamp=stamp, media=item, defaults={"role": link["role"], "position": link["position"]}
                )

    def store_media(self, item: dict, name: str):
        root = storage.media_root()
        root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=root, prefix=".import-")
        tmp = Path(tmp)
        try:
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as out, self.zf.open(name) as src:
                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                    digest.update(chunk)
                    out.write(chunk)
            sha = digest.hexdigest()
            try:
                info = storage.inspect(tmp)
            except storage.InvalidImage:
                return None
            key = storage.storage_key(self.user.id, sha, info["ext"])
            storage.store(tmp, key)
            self.stored.append(root / key)
            media_id, _ = self.free_id(Media, item["id"])
            created = Media.objects.create(
                id=media_id,
                user=self.user,
                sha256=sha,
                mime=info["mime"],
                bytes=(root / key).stat().st_size,
                width=info["width"],
                height=info["height"],
                taken_at=parse_datetime(item["taken_at"]) if item.get("taken_at") else info["taken_at"],
                storage_key=key,
            )
            self.stats["media"] += 1
            return created
        finally:
            tmp.unlink(missing_ok=True)
