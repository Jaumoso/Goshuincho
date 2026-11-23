import io
import uuid
from datetime import date, timedelta

import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.utils import timezone
from PIL import Image

from accounts.models import User
from geo.models import Prefecture, Region
from places.models import Place
from visits.models import Goshuincho, Stamp, Visit

pytestmark = pytest.mark.django_db


@pytest.fixture
def kyoto():
    region = Region.objects.create(id=5, slug="kansai", name_ja="近畿", name_en="Kansai", name_es="Kansai")
    return Prefecture.objects.create(
        id=26, iso_code="JP-26", region=region, name_ja="京都府", name_romaji="Kyōto",
        name_en="Kyoto", name_es="Kioto",
    )


@pytest.fixture
def temple(kyoto):
    return Place.objects.create(
        kind="temple", name_ja="東寺", name_romaji="Tō-ji", prefecture=kyoto,
        location=Point(135.7477, 34.9806, srid=4326),
    )


@pytest.fixture
def taro():
    return User.objects.create_user("taro@example.com", "pw-taro-12345", display_name="Taro")


@pytest.fixture
def hanako():
    return User.objects.create_user("hanako@example.com", "pw-hanako-12345", display_name="Hanako")


@pytest.fixture
def api(taro):
    client = Client()
    client.force_login(taro)
    return client


@pytest.fixture
def media_dir(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def post(client, url, data):
    return client.post(url, data, content_type="application/json")


def jpeg_bytes(color="red", size=(800, 600)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def test_visit_date_precision_and_future(api, temple):
    url = f"/api/places/{temple.id}/visits"
    cases = [
        ({"visited_on": "2019-07-15", "visited_precision": "month"}, "2019-07-01"),
        ({"visited_on": "2019-07-15", "visited_precision": "season"}, "2019-06-01"),
        ({"visited_on": "2020-02-10", "visited_precision": "season"}, "2019-12-01"),
        ({"visited_on": "2019-07-15", "visited_precision": "year"}, "2019-01-01"),
        ({"visited_precision": "unknown", "visited_on": "2019-07-15"}, None),
    ]
    for payload, expected in cases:
        response = post(api, url, payload)
        assert response.status_code == 201, response.content
        assert response.json()["visited_on"] == expected

    tomorrow = timezone.localdate() + timedelta(days=1)
    assert post(api, url, {"visited_on": tomorrow.isoformat()}).json()["detail"] == "date_in_future"
    assert post(api, url, {"visited_precision": "day"}).status_code == 422


def test_precision_check_in_database(taro, temple):
    with pytest.raises(IntegrityError), transaction.atomic():
        Visit.objects.create(user=taro, place=temple, visited_on=date(2019, 7, 5), visited_precision="month")


def test_visit_idempotent_and_summary(api, temple):
    url = f"/api/places/{temple.id}/visits"
    vid = str(uuid.uuid4())
    first = post(api, url, {"id": vid, "visited_on": "2019-06-01", "visited_precision": "season",
                            "stamps": [{"kind": "goshuin"}]})
    assert first.status_code == 201
    again = post(api, url, {"id": vid, "visited_on": "2019-06-01", "visited_precision": "season"})
    assert again.status_code == 200 and len(again.json()["stamps"]) == 1

    post(api, url, {"visited_on": "2025-10-12", "stamps": [{"kind": "goshuin"}, {"kind": "goshuin_limited"}]})
    post(api, url, {"kind": "mail", "visited_on": "2025-11-01", "stamps": [{"kind": "goshuin"}]})

    mine = api.get(f"/api/places/{temple.id}").json()["mine"]
    assert mine["visit_count"] == 2
    assert mine["stamp_count"] == 4
    assert mine["last_visit"] == "2025-10-12" and mine["last_visit_precision"] == "day"
    assert mine["first_visit"] == "2019-06-01" and mine["first_visit_precision"] == "season"
    assert len(api.get(url).json()) == 3


def test_soft_delete_visit_hides_stamps(api, temple):
    visit = post(api, f"/api/places/{temple.id}/visits",
                 {"visited_on": "2024-04-01", "stamps": [{"kind": "goshuin"}]}).json()
    assert api.delete(f"/api/visits/{visit['id']}").status_code == 204
    assert api.get("/api/stamps").json()["count"] == 0
    assert Stamp.objects.get(visit_id=visit["id"]).deleted_at is not None
    assert api.get(f"/api/places/{temple.id}").json()["mine"]["visit_count"] == 0


def test_composite_foreign_keys(taro, hanako, temple):
    visit = Visit.objects.create(user=taro, place=temple, visited_on=date(2024, 1, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        Stamp.objects.create(visit=visit, user=hanako, place=temple)

    book = Goshuincho.objects.create(user=hanako, name="Libreta de Hanako")
    with pytest.raises(IntegrityError), transaction.atomic():
        Stamp.objects.create(visit=visit, user=taro, place=temple, goshuincho=book)

    own = Goshuincho.objects.create(user=taro, name="Mía")
    stamp = Stamp.objects.create(visit=visit, user=taro, place=temple, goshuincho=own)
    own.delete()
    stamp.refresh_from_db()
    assert stamp.goshuincho_id is None and stamp.user_id == taro.id


def test_stamp_api_rejects_foreign_goshuincho(api, hanako, temple):
    book = Goshuincho.objects.create(user=hanako, name="Ajena")
    response = post(api, f"/api/places/{temple.id}/visits",
                    {"visited_on": "2024-01-01", "stamps": [{"goshuincho_id": str(book.id)}]})
    assert response.status_code == 422
    assert not Visit.objects.exists()


def test_pending_places_are_private(api, hanako, kyoto, temple):
    created = post(api, "/api/places", {"kind": "shrine", "name_ja": "小さな神社", "lat": 35.0, "lon": 135.76,
                                        "prefecture_id": kyoto.id})
    assert created.status_code == 201
    place = created.json()
    assert place["status"] == "pending" and place["is_mine"]

    other = Client()
    other.force_login(hanako)
    assert other.get(f"/api/places/{place['id']}").status_code == 404
    assert other.get("/api/places").json()["count"] == 1
    assert api.get("/api/places").json()["count"] == 2

    post(api, f"/api/places/{place['id']}/visits", {"visited_on": "2024-01-01"})
    assert api.delete(f"/api/places/{place['id']}").json()["detail"] == "place_has_visits"
    assert api.delete(f"/api/places/{temple.id}").status_code == 403


def test_search_and_filters(api, temple):
    assert api.get("/api/places?q=toji").json()["count"] == 1
    assert api.get("/api/places?q=東寺").json()["count"] == 1
    assert api.get("/api/places?q=kinkaku").json()["count"] == 0
    assert api.get("/api/places?state=unvisited").status_code == 422
    bbox = "135.7,34.9,135.8,35.1"
    assert api.get(f"/api/places?state=unvisited&bbox={bbox}").json()["count"] == 1

    api.put(f"/api/places/{temple.id}/mine", {"wishlist": True}, content_type="application/json")
    assert api.get("/api/places?state=wishlist").json()["count"] == 1
    post(api, f"/api/places/{temple.id}/visits", {"visited_on": "2024-01-01"})
    assert api.get("/api/places?state=visited").json()["items"][0]["mine"]["visit_count"] == 1

    similar = api.get("/api/places/similar?name=Toji&lat=34.981&lon=135.748").json()
    assert similar and similar[0]["id"] == str(temple.id)


def test_media_upload_dedupe_and_owner(api, hanako, media_dir):
    data = jpeg_bytes()
    first = api.post("/api/media", {"file": io.BytesIO(data)})
    assert first.status_code == 201, first.content
    media = first.json()
    assert media["mime"] == "image/jpeg" and media["width"] == 800

    second = api.post("/api/media", {"file": io.BytesIO(data)})
    assert second.status_code == 200 and second.json()["id"] == media["id"]

    thumb = api.get(f"/api/media/{media['id']}/thumb")
    assert thumb.status_code == 200 and thumb["Content-Type"] == "image/webp"
    with Image.open(io.BytesIO(b"".join(thumb.streaming_content))) as img:
        assert max(img.size) == 320

    other = Client()
    other.force_login(hanako)
    assert other.get(f"/api/media/{media['id']}/original").status_code == 404

    bad = api.post("/api/media", {"file": io.BytesIO(b"%PDF-1.4 not an image")})
    assert bad.status_code == 415


def test_media_size_limit(api, media_dir, settings):
    settings.MAX_UPLOAD_MB = 0
    assert api.post("/api/media", {"file": io.BytesIO(jpeg_bytes())}).status_code == 413


def test_visit_with_photo_and_collection(api, temple, media_dir):
    media_id = api.post("/api/media", {"file": io.BytesIO(jpeg_bytes("blue"))}).json()["id"]
    visit = post(api, f"/api/places/{temple.id}/visits", {
        "visited_on": "2025-10-12",
        "stamps": [{"kind": "goshuin", "title": "  Goshuin de Kōbō Daishi ", "media": [{"media_id": media_id}]}],
    }).json()
    stamp = visit["stamps"][0]
    assert stamp["title"] == "Goshuin de Kōbō Daishi" and stamp["media"][0]["id"] == media_id

    page = api.get("/api/stamps?year=2025").json()
    assert page["count"] == 1 and page["items"][0]["place"]["name_ja"] == "東寺"
    assert api.get("/api/stamps?year=2024").json()["count"] == 0

    stats = api.get("/api/stats/summary").json()
    assert stats["places_visited"] == 1 and stats["goshuin"] == 1 and stats["by_year"][0]["key"] == "2025"


def test_trigram_extension_and_view_exist():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        assert cursor.fetchone()
        cursor.execute("SELECT 1 FROM pg_views WHERE viewname = 'user_place_summary'")
        assert cursor.fetchone()


def test_seed_categories_and_csv_import():
    call_command("seed")
    call_command("import_places_csv", sample=True)
    toji = Place.objects.get(name_ja="東寺")
    assert toji.prefecture_id == 26 and toji.source == "csv"
    assert Place.objects.get(name_ja="清水寺").placecategory_set.get(category__slug="saigoku-kannon").seq == 16
    count = Place.objects.count()
    call_command("import_places_csv", sample=True)
    assert Place.objects.count() == count
