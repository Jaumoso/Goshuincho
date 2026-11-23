"""Importador de OpenStreetMap: extractos regionales de Geofabrik filtrados localmente con pyosmium."""

import logging
import re
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from django.contrib.gis.geos import GEOSException, GEOSGeometry, Point
from django.db import transaction
from django.utils import timezone

from geo.models import Prefecture, Region

from .models import OsmImport, Place, PlaceKind, PlaceSource, ReviewStatus

logger = logging.getLogger(__name__)

GEOFABRIK_URL = "https://download.geofabrik.de/asia/japan/{}-latest.osm.pbf"
# Región del seed -> extracto de Geofabrik (Kyūshū incluye Okinawa).
REGION_EXTRACTS = {
    "hokkaido": "hokkaido",
    "tohoku": "tohoku",
    "kanto": "kanto",
    "chubu": "chubu",
    "kansai": "kansai",
    "chugoku": "chugoku",
    "shikoku": "shikoku",
    "kyushu-okinawa": "kyushu",
}
RELIGION_KIND = {"shinto": PlaceKind.SHRINE, "buddhist": PlaceKind.TEMPLE}
LINK_DISTANCE_DEG = 0.01  # ~1 km: enlaza lugares del CSV o manuales con su elemento de OSM
BATCH = 2000

JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
# Sufijos que se separan al generar romaji: «八坂神社» -> «Yasaka Jinja».
# (sufijo, romaji, separador): "Yasaka Jinja", "Ryōzen-ji".
SUFFIXES = [
    ("八幡神社", "Hachiman Jinja", " "),
    ("八幡宮", "Hachimangū", " "),
    ("天満宮", "Tenmangū", " "),
    ("神社", "Jinja", " "),
    ("大社", "Taisha", " "),
    ("神宮", "Jingū", " "),
    ("稲荷", "Inari", " "),
    ("駅", "Eki", " "),
    ("寺", "ji", "-"),
    ("院", "in", "-"),
    ("堂", "dō", "-"),
]
LONG_VOWELS = [("ou", "ō"), ("oo", "ō"), ("uu", "ū")]
WORD_SPLIT = re.compile(r"[\s・･()（）「」]+")

# Selectores de variante (IVS): pykakasi falla con ellos y no cambian la lectura.
VARIATION_SELECTORS = re.compile("[\ufe00-\ufe0f\U000e0100-\U000e01ef]")

_kakasi = None


def _convert(text: str) -> list[dict]:
    global _kakasi
    if _kakasi is None:
        import pykakasi

        _kakasi = pykakasi.kakasi()
    text = VARIATION_SELECTORS.sub("", text)
    try:
        return _kakasi.convert(text)
    except (IndexError, KeyError):
        # Último recurso: carácter a carácter, omitiendo los que pykakasi no sepa leer.
        items = []
        for char in text:
            try:
                items += _kakasi.convert(char)
            except (IndexError, KeyError):
                pass
        return items


def _romaji_word(text: str) -> str:
    word = ""
    for item in _convert(text):
        segment = item["hepburn"].strip()
        for long, macron in LONG_VOWELS:
            segment = segment.replace(long, macron)
        word += segment
    return word[:1].upper() + word[1:]


def romanize(text: str) -> str:
    """Romaji Hepburn aproximado y sin conexión (pykakasi), con macrones para vocales largas.

    Cada palabra japonesa se translitera junta ("照護寺" → "Shōgo-ji") y los sufijos habituales
    de santuarios, templos y estaciones se separan.
    """
    words = []
    for part in WORD_SPLIT.split(VARIATION_SELECTORS.sub("", text)):
        if not part:
            continue
        for ja, ro, sep in SUFFIXES:
            if part.endswith(ja) and len(part) > len(ja):
                base = _romaji_word(part[: -len(ja)])
                words.append(f"{base}{sep}{ro}")
                break
        else:
            words.append(_romaji_word(part))
    return " ".join(w for w in words if w)


@dataclass
class Element:
    osm_type: str
    osm_id: int
    lon: float
    lat: float
    tags: dict = field(repr=False)


def kind_for(tags: dict) -> str | None:
    if tags.get("amenity") == "place_of_worship":
        return RELIGION_KIND.get(tags.get("religion", ""))
    if tags.get("railway") == "station":
        return PlaceKind.STATION
    return None


def read_elements(path: Path) -> Iterator[Element]:
    """Templos, santuarios y estaciones con nombre; las áreas se reducen a un punto interior."""
    import osmium

    wkb = osmium.geom.WKBFactory()
    processor = (
        osmium.FileProcessor(str(path))
        .with_locations()
        .with_areas(osmium.filter.KeyFilter("name"))
        .with_filter(osmium.filter.KeyFilter("name"))
        .with_filter(osmium.filter.TagFilter(("amenity", "place_of_worship"), ("railway", "station")))
    )
    for obj in processor:
        tags = dict(obj.tags)
        if kind_for(tags) is None:
            continue
        try:
            if obj.is_node():
                if obj.location.valid():
                    yield Element("node", obj.id, obj.location.lon, obj.location.lat, tags)
            elif obj.is_area():
                point = GEOSGeometry(wkb.create_multipolygon(obj)).point_on_surface
                osm_type = "way" if obj.from_way() else "relation"
                yield Element(osm_type, obj.orig_id(), point.x, point.y, tags)
            elif obj.is_way() and not obj.is_closed():
                line = GEOSGeometry(wkb.create_linestring(obj))
                point = line.interpolate_normalized(0.5)
                yield Element("way", obj.id, point.x, point.y, tags)
        except (RuntimeError, GEOSException) as exc:  # geometrías rotas o nodos fuera del extracto
            logger.debug("OSM %s ignorado: %s", obj.id, exc)


def place_fields(el: Element) -> dict:
    tags = el.tags
    name = tags.get("name", "").strip()
    name_ja = (tags.get("name:ja") or (name if JAPANESE.search(name) else "")).strip() or None
    romaji = (tags.get("name:ja-Latn") or tags.get("name:ja_rm") or "").strip() or None
    name_en = (tags.get("name:en") or "").strip() or None
    if not name_ja and not romaji and not name_en:
        name_en = name or None
    generated = False
    if not romaji and name_ja:
        romaji, generated = romanize(name_ja) or None, True
    alt = [
        tags[k].strip()
        for k in ("name:ja-Hira", "name:ja_kana", "alt_name", "old_name", "official_name")
        if tags.get(k, "").strip() and tags[k].strip() not in (name_ja, romaji, name_en)
    ]
    return {
        "kind": kind_for(tags),
        "name_ja": name_ja,
        "name_romaji": romaji,
        "name_en": name_en,
        "name_romaji_generated": generated,
        "alt_names": alt,
        "tradition": (tags.get("denomination") or "").strip() or None,
        "operator": (tags.get("operator") or "").strip() or None,
        "website": (tags.get("website") or tags.get("contact:website") or "").strip() or None,
        "location": Point(round(el.lon, 7), round(el.lat, 7), srid=4326),
    }


class PrefectureLocator:
    """Punto en polígono en memoria contra los contornos simplificados; si no cae dentro, la más cercana."""

    def __init__(self):
        self.items = [(p.id, p.boundary.prepared, p.boundary) for p in Prefecture.objects.exclude(boundary=None)]

    def __call__(self, point: Point) -> int:
        for pid, prepared, _ in self.items:
            if prepared.contains(point):
                return pid
        return min(self.items, key=lambda item: item[2].distance(point))[0]


def download(slug: str, directory: Path, log: Callable[[str], None]) -> Path:
    url = GEOFABRIK_URL.format(slug)
    target = directory / f"{slug}.osm.pbf"
    log(f"Descargando {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "Goshuincho OSM importer"})
    with urllib.request.urlopen(request, timeout=60) as response, open(target, "wb") as fh:
        shutil.copyfileobj(response, fh, length=1 << 20)
    log(f"Descargados {target.stat().st_size / 1e6:.0f} MB")
    return target


UPDATABLE = [
    "kind",
    "name_ja",
    "name_romaji",
    "name_en",
    "name_romaji_generated",
    "alt_names",
    "tradition",
    "operator",
    "website",
    "location",
    "prefecture_id",
    "osm_missing",
]


def _changed(place: Place, fields: dict) -> bool:
    for name, value in fields.items():
        current = getattr(place, name)
        if name == "location":
            if current is None or current.coords != value.coords:
                return True
        elif current != value:
            return True
    return False


def import_region(region: Region, path: Path | None = None, log: Callable[[str], None] = logger.info) -> dict:
    """Importa o actualiza los lugares de OSM de una región. Devuelve los contadores."""
    slug = REGION_EXTRACTS[region.slug]
    with tempfile.TemporaryDirectory(prefix="osm-") as tmp:
        if path is None:
            path = download(slug, Path(tmp), log)
        log(f"Leyendo {path.name}")
        locate = PrefectureLocator()
        elements = {}
        for el in read_elements(path):
            fields = place_fields(el)
            fields["prefecture_id"] = locate(fields["location"])
            elements[(el.osm_type, el.osm_id)] = fields
    log(f"{len(elements)} elementos con nombre")
    return save_elements(region, elements, log)


def _names_match(a: str | None, b: str | None, exact: bool) -> bool:
    """"霊山寺" enlaza con "第1番札所 霊山寺": iguales o, en la segunda pasada, uno contiene al otro."""
    if not a or not b:
        return False
    if exact:
        return a == b
    short, long = sorted((a, b), key=len)
    return len(short) >= 2 and short in long


def _find_links(candidates: dict[str, list[Place]], elements: dict) -> dict:
    """Enlaza cada lugar sin OSM con el elemento más cercano (< ~1 km) del mismo tipo y nombre.

    Primero por nombre exacto y luego por inclusión, para que "東寺" prefiera el templo y no "東寺観音堂".
    """
    links: dict[tuple[str, int], Place] = {}
    for exact in (True, False):
        for kind, places in candidates.items():
            for place in list(places):
                best, best_dist = None, LINK_DISTANCE_DEG
                for key, fields in elements.items():
                    loc = fields["location"]
                    if key in links or fields["kind"] != kind:
                        continue
                    if abs(place.location.x - loc.x) > LINK_DISTANCE_DEG or abs(place.location.y - loc.y) > LINK_DISTANCE_DEG:
                        continue
                    if not _names_match(place.name_ja, fields["name_ja"], exact):
                        continue
                    dist = place.location.distance(loc)
                    if dist <= best_dist:
                        best, best_dist = key, dist
                if best:
                    links[best] = place
                    places.remove(place)
    return links


@transaction.atomic
def save_elements(region: Region, elements: dict, log: Callable[[str], None] = logger.info) -> dict:
    counts = {"created": 0, "updated": 0, "linked": 0, "missing": 0, "total": len(elements)}
    existing = {}
    keys = list(elements)
    for i in range(0, len(keys), BATCH):
        chunk = keys[i : i + BATCH]
        ids = [k[1] for k in chunk]
        for place in Place.objects.filter(osm_id__in=ids):
            existing[(place.osm_type, place.osm_id)] = place

    # Lugares sin OSM (CSV, manuales) que pueden enlazarse por tipo, nombre japonés y distancia.
    candidates: dict[str, list[Place]] = {}
    for place in Place.objects.filter(
        osm_id__isnull=True, location__isnull=False, name_ja__isnull=False, status=ReviewStatus.APPROVED
    ).exclude(source=PlaceSource.USER):
        candidates.setdefault(place.kind, []).append(place)
    new = {k: f for k, f in elements.items() if k not in existing}
    links = _find_links(candidates, new)

    to_create, to_update = [], []
    for (osm_type, osm_id), fields in elements.items():
        fields = {**fields, "osm_missing": False}
        place = existing.get((osm_type, osm_id))
        if place is None:
            place = links.get((osm_type, osm_id))
            if place:
                place.osm_type, place.osm_id, place.locally_modified = osm_type, osm_id, True
                for name, value in fields.items():
                    if name not in ("location", "prefecture_id", "kind") and not getattr(place, name):
                        setattr(place, name, value)
                to_update.append(place)
                counts["linked"] += 1
                continue
            to_create.append(Place(**fields, osm_type=osm_type, osm_id=osm_id, source=PlaceSource.OSM))
            continue
        if place.locally_modified:
            fields = {"osm_missing": False}
        if _changed(place, fields):
            for name, value in fields.items():
                setattr(place, name, value)
            to_update.append(place)
            counts["updated"] += 1

    now = timezone.now()
    for place in to_update:
        place.updated_at = now
    Place.objects.bulk_create(to_create, batch_size=BATCH)
    Place.objects.bulk_update(
        to_update, [*UPDATABLE, "osm_type", "osm_id", "locally_modified", "updated_at"], batch_size=BATCH
    )
    counts["created"] = len(to_create)

    seen = set(elements)
    missing = [
        pid
        for pid, osm_type, osm_id in Place.objects.filter(
            osm_id__isnull=False, osm_missing=False, prefecture__region=region
        ).values_list("id", "osm_type", "osm_id")
        if (osm_type, osm_id) not in seen
    ]
    Place.objects.filter(id__in=missing).update(osm_missing=True, updated_at=now)
    counts["missing"] = len(missing)
    log(
        "Creados {created}, actualizados {updated}, enlazados {linked}, "
        "marcados como desaparecidos {missing}".format(**counts)
    )
    return counts


def run_import(job: OsmImport, path: Path | None = None, log: Callable[[str], None] = logger.info) -> OsmImport:
    job.status, job.started_at, job.error = OsmImport.Status.RUNNING, timezone.now(), ""
    job.save(update_fields=["status", "started_at", "error"])
    try:
        counts = import_region(job.region, path, log)
    except Exception as exc:
        job.status, job.error = OsmImport.Status.FAILED, f"{type(exc).__name__}: {exc}"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise
    job.status, job.finished_at = OsmImport.Status.DONE, timezone.now()
    for name in ("created", "updated", "linked", "missing", "total"):
        setattr(job, name, counts[name])
    job.save()
    return job
