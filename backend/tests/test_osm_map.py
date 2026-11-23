import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import Client

from accounts.models import User
from geo.models import Prefecture, Region
from places.models import Place, UserPlace
from places.osm import Element, import_region, place_fields, romanize, save_elements
from visits.models import Visit

pytestmark = pytest.mark.django_db


@pytest.fixture
def kyoto():
    region = Region.objects.create(id=5, slug="kansai", name_ja="近畿", name_en="Kansai", name_es="Kansai")
    return Prefecture.objects.create(
        id=26, iso_code="JP-26", region=region, name_ja="京都府", name_romaji="Kyōto", name_en="Kyoto",
        name_es="Kioto", boundary=MultiPolygon(Polygon.from_bbox((135.0, 34.7, 136.1, 35.8)), srid=4326),
    )


@pytest.fixture
def taro():
    return User.objects.create_user("taro@example.com", "pw-taro-12345", display_name="Taro")


@pytest.fixture
def api(taro):
    client = Client()
    client.force_login(taro)
    return client


def fields_for(osm_id, name, lon=135.75, lat=35.0, **tags):
    el = Element("node", osm_id, lon, lat, {"amenity": "place_of_worship", "religion": "buddhist", "name": name, **tags})
    return {**place_fields(el), "prefecture_id": 26}


def test_romanize():
    assert romanize("照護寺") == "Shōgo-ji"
    assert romanize("八坂神社") == "Yasaka Jinja"
    assert romanize("太宰府天満宮") == "Dazaifu Tenmangū"
    assert romanize("延暦寺 根本中堂").startswith("Enryaku-ji ")
    # Kanji con selector de variante (IVS): pykakasi fallaba y abortaba toda la importación.
    assert romanize("葛\U000e0100城神社") == romanize("葛城神社")


def test_place_fields_names():
    f = fields_for(1, "八坂神社", religion="shinto", **{"name:en": "Yasaka Shrine", "name:ja-Hira": "やさかじんじゃ"})
    assert (f["kind"], f["name_ja"], f["name_romaji"], f["name_romaji_generated"]) == (
        "shrine", "八坂神社", "Yasaka Jinja", True,
    )
    assert f["name_en"] == "Yasaka Shrine" and f["alt_names"] == ["やさかじんじゃ"]
    f = fields_for(2, "東寺", **{"name:ja-Latn": "Tō-ji"})
    assert (f["name_romaji"], f["name_romaji_generated"]) == ("Tō-ji", False)


def test_save_elements_create_update_missing_and_local_edits(kyoto):
    region = kyoto.region
    elements = {("node", 1): fields_for(1, "東寺"), ("node", 2): fields_for(2, "清水寺", lon=135.78)}
    assert save_elements(region, elements)["created"] == 2
    assert save_elements(region, elements)["updated"] == 0  # idempotente

    Place.objects.filter(osm_id=2).update(name_romaji="Kiyomizu-dera", locally_modified=True)
    elements[("node", 1)] = fields_for(1, "教王護国寺")
    elements[("node", 2)] = fields_for(2, "清水寺", lon=135.79)
    counts = save_elements(region, elements)
    assert counts["updated"] == 1
    assert Place.objects.get(osm_id=1).name_ja == "教王護国寺"
    kiyomizu = Place.objects.get(osm_id=2)
    assert kiyomizu.name_romaji == "Kiyomizu-dera" and kiyomizu.location.x == 135.78

    counts = save_elements(region, {("node", 1): elements[("node", 1)]})
    assert counts["missing"] == 1
    assert Place.objects.get(osm_id=2).osm_missing  # nunca se borra
    save_elements(region, elements)
    assert not Place.objects.get(osm_id=2).osm_missing


def test_save_elements_links_existing_places_preferring_exact_names(kyoto):
    csv = Place.objects.create(
        kind="temple", name_ja="東寺", name_romaji="Tō-ji", prefecture=kyoto, source="csv",
        location=Point(135.7477, 34.9806, srid=4326),
    )
    far = Place.objects.create(
        kind="temple", name_ja="霊山寺", prefecture=kyoto, source="csv", location=Point(135.9, 35.5, srid=4326)
    )
    elements = {
        ("way", 10): fields_for(10, "東寺観音堂", lon=135.7476, lat=34.9805),
        ("way", 11): fields_for(11, "東寺", lon=135.748, lat=34.981, website="https://toji.or.jp"),
        ("node", 12): fields_for(12, "第1番札所 霊山寺", lon=135.75, lat=35.0),
    }
    counts = save_elements(kyoto.region, elements)
    assert (counts["linked"], counts["created"]) == (1, 2)
    csv.refresh_from_db()
    assert (csv.osm_type, csv.osm_id, csv.locally_modified) == ("way", 11, True)
    assert csv.name_romaji == "Tō-ji" and csv.website == "https://toji.or.jp"
    far.refresh_from_db()
    assert far.osm_id is None


def test_import_region_reads_nodes_and_areas(kyoto, tmp_path):
    pbf = tmp_path / "kansai.osm"
    pbf.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
  <node id="1" version="1" lat="35.0" lon="135.70"><tag k="amenity" v="place_of_worship"/>
    <tag k="religion" v="shinto"/><tag k="name" v="八坂神社"/></node>
  <node id="2" version="1" lat="35.0" lon="135.75"/>
  <node id="3" version="1" lat="35.0" lon="135.76"/>
  <node id="4" version="1" lat="35.01" lon="135.76"/>
  <node id="5" version="1" lat="35.01" lon="135.75"/>
  <node id="6" version="1" lat="35.0" lon="135.80"><tag k="amenity" v="place_of_worship"/>
    <tag k="religion" v="christian"/><tag k="name" v="教会"/></node>
  <node id="7" version="1" lat="35.0" lon="135.81"><tag k="railway" v="station"/></node>
  <way id="20" version="1"><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="5"/><nd ref="2"/>
    <tag k="amenity" v="place_of_worship"/><tag k="religion" v="buddhist"/><tag k="name" v="東寺"/></way>
</osm>
"""
    )
    counts = import_region(kyoto.region, pbf)
    assert counts["created"] == 2
    toji = Place.objects.get(osm_type="way", osm_id=20)
    assert toji.kind == "temple" and toji.prefecture_id == 26
    assert 135.75 < toji.location.x < 135.76 and 35.0 < toji.location.y < 35.01
    assert Place.objects.get(osm_type="node", osm_id=1).kind == "shrine"


def test_map_points(api, taro, kyoto):
    def make(name, lon, lat):
        return Place.objects.create(kind="temple", name_ja=name, prefecture=kyoto, location=Point(lon, lat, srid=4326))

    visited, wished, near, far = make("一", 135.7, 35.0), make("二", 135.0, 34.7), make("三", 135.71, 35.01), make("四", 140.0, 38.0)
    Visit.objects.create(user=taro, place=visited, kind="in_person", visited_precision="unknown")
    UserPlace.objects.create(user=taro, place=wished, wishlist=True)

    items = api.get("/api/places/map").json()["items"]
    assert [(i["id"], i["state"]) for i in items] == [(str(visited.id), "visited"), (str(wished.id), "wishlist")]

    items = api.get("/api/places/map", {"bbox": "135.6,34.9,135.8,35.1"}).json()["items"]
    assert {i["id"]: i["state"] for i in items} == {str(visited.id): "visited", str(wished.id): "wishlist", str(near.id): "unvisited"}

    items = api.get("/api/places/map", {"bbox": "125,30,145,45"}).json()["items"]
    assert str(far.id) not in {i["id"] for i in items}  # zona demasiado grande: sin no visitados
    assert api.get("/api/places/map", {"bbox": "1,2,0,3"}).status_code == 422


@pytest.fixture
def tiles(settings, tmp_path):
    settings.TILES_DIR = tmp_path
    (tmp_path / "japan.pmtiles").write_bytes(bytes(range(256)) * 4)
    return Client()


def test_tiles_ranges(tiles):
    r = tiles.get("/tiles/japan.pmtiles", HTTP_RANGE="bytes=10-19")
    assert r.status_code == 206 and b"".join(r.streaming_content) == bytes(range(10, 20))
    assert r["Content-Range"] == "bytes 10-19/1024" and r["Accept-Ranges"] == "bytes"

    r = tiles.get("/tiles/japan.pmtiles", HTTP_RANGE="bytes=-4")
    assert r.status_code == 206 and b"".join(r.streaming_content) == bytes([252, 253, 254, 255])
    assert tiles.get("/tiles/japan.pmtiles", HTTP_RANGE="bytes=2000-").status_code == 416

    full = tiles.get("/tiles/japan.pmtiles")
    assert full.status_code == 200 and len(b"".join(full.streaming_content)) == 1024
    assert tiles.get("/tiles/japan.pmtiles", HTTP_IF_NONE_MATCH=full["ETag"]).status_code == 304
    assert tiles.head("/tiles/japan.pmtiles").status_code == 200
    assert tiles.get("/tiles/missing.pmtiles").status_code == 404
    assert tiles.get("/tiles/.env").status_code == 404
