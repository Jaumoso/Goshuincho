import io
import json
import zipfile

import pytest
from django.contrib.gis.geos import Point
from django.test import Client

from accounts.models import User
from places.models import Place, UserPlace
from visits.models import Goshuincho, Media, Stamp, Visit

from .test_places_visits import jpeg_bytes, kyoto, post, temple  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def media_dir(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def client_for(user):
    client = Client()
    client.force_login(user)
    return client


def make_collection(client, kyoto, temple):  # noqa: F811
    book = post(client, "/api/goshuincho", {"name": "Primera libreta", "started_on": "2024-04-01"}).json()
    media_id = client.post("/api/media", {"file": io.BytesIO(jpeg_bytes("green"))}).json()["id"]
    post(client, f"/api/places/{temple.id}/visits", {
        "visited_on": "2024-04-03",
        "notes": "Pagoda",
        "media": [media_id],
        "stamps": [{"kind": "goshuin", "title": "Kōbō Daishi", "goshuincho_id": book["id"],
                    "media": [{"media_id": media_id, "role": "front"}]}],
    })
    own = post(client, "/api/places", {
        "kind": "shrine", "name_ja": "小さな神社", "prefecture_id": kyoto.id, "lat": 35.01, "lon": 135.76,
    })
    assert own.status_code == 201, own.content
    post(client, f"/api/places/{own.json()['id']}/visits", {"visited_on": "2024-06-01", "visited_precision": "year"})
    client.put(f"/api/places/{temple.id}/mine", {"wishlist": True, "notes": "Volver en otoño"},
                 content_type="application/json")
    return own.json()["id"]


def export_zip(client) -> bytes:
    response = client.post("/api/export")
    assert response.status_code == 200 and response["Content-Type"] == "application/zip"
    return b"".join(response.streaming_content)


def import_zip(client, data: bytes):
    upload = io.BytesIO(data)
    upload.name = "copia.zip"
    return client.post("/api/import", {"file": upload})


def test_export_contents(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    api = client_for(taro)
    make_collection(api, kyoto, temple)
    with zipfile.ZipFile(io.BytesIO(export_zip(api))) as zf:
        data = json.loads(zf.read("data.json"))
        assert data["format"] == "goshuincho-export" and data["user"]["email"] == "taro@example.com"
        assert len(data["visits"]) == 2 and len(data["stamps"]) == 1 and len(data["goshuincho"]) == 1
        assert {p["own"] for p in data["places"]} == {True, False}
        assert data["user_places"][0]["wishlist"] is True
        assert data["media"][0]["file"] in zf.namelist()


def test_import_into_other_user_is_idempotent(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    hanako = User.objects.create_user("hanako@example.com", "pw-hanako-12345")
    own_id = make_collection(client_for(taro), kyoto, temple)
    archive = export_zip(client_for(taro))

    other = client_for(hanako)
    result = import_zip(other, archive)
    assert result.status_code == 200, result.content
    assert result.json() == {"places_created": 1, "places_matched": 1, "visits": 2, "stamps": 1,
                             "media": 1, "goshuincho": 1}
    stamp = Stamp.objects.get(user=hanako)
    assert stamp.place_id == temple.id and stamp.goshuincho.user_id == hanako.id
    assert stamp.media.get().user_id == hanako.id
    copy = Place.objects.get(created_by=hanako)
    assert str(copy.id) != own_id and copy.status == "pending" and copy.name_ja == "小さな神社"
    assert UserPlace.objects.get(user=hanako, place=temple).wishlist
    assert other.get(f"/api/media/{stamp.media.get().id}/original").status_code == 200

    again = import_zip(other, archive).json()
    assert again["visits"] == again["stamps"] == again["media"] == again["places_created"] == 0
    assert Visit.objects.filter(user=hanako).count() == 2
    assert Visit.objects.filter(user=taro).count() == 2


def test_restore_after_wipe_keeps_ids(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    api = client_for(taro)
    own_id = make_collection(api, kyoto, temple)
    archive = export_zip(api)
    visit_ids = set(Visit.objects.filter(user=taro).values_list("id", flat=True))

    Visit.objects.filter(user=taro).delete()
    Media.objects.filter(user=taro).delete()
    Goshuincho.objects.filter(user=taro).delete()
    UserPlace.objects.filter(user=taro).delete()
    Place.objects.filter(id=own_id).delete()

    assert import_zip(api, archive).json()["places_created"] == 1
    assert set(Visit.objects.filter(user=taro).values_list("id", flat=True)) == visit_ids
    assert str(Place.objects.get(created_by=taro).id) == own_id
    assert api.get("/api/stats/summary").json()["goshuin"] == 1


def test_import_matches_by_osm_and_name(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    api = client_for(taro)
    post(api, f"/api/places/{temple.id}/visits", {"visited_on": "2024-04-03"})
    archive = export_zip(api)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        data = json.loads(zf.read("data.json"))
    # Otra instancia: el mismo templo tiene otro id.
    Visit.objects.all().delete()
    temple.delete()
    Place.objects.create(kind="temple", name_romaji="Tō-ji", prefecture=kyoto,
                         location=Point(135.7480, 34.9808, srid=4326))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(data))
    result = import_zip(api, buf.getvalue()).json()
    assert result["places_matched"] == 1 and result["places_created"] == 0


def test_import_rejects_bad_archive(media_dir):
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    response = import_zip(client_for(taro), b"not a zip")
    assert response.status_code == 400 and response.json()["detail"] == "invalid_archive"


def test_change_password_and_delete_account(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    api = client_for(taro)
    make_collection(api, kyoto, temple)

    wrong = post(api, "/api/me/password", {"current_password": "nope", "new_password": "otra-clave-larga-1"})
    assert wrong.status_code == 403
    weak = post(api, "/api/me/password", {"current_password": "pw-taro-12345", "new_password": "123"})
    assert weak.status_code == 400
    ok = post(api, "/api/me/password", {"current_password": "pw-taro-12345", "new_password": "otra-clave-larga-1"})
    assert ok.status_code == 204 and api.get("/api/me").status_code == 200

    assert post(api, "/api/me/delete", {"password": "pw-taro-12345"}).status_code == 403
    assert post(api, "/api/me/delete", {"password": "otra-clave-larga-1"}).status_code == 204
    assert not User.objects.filter(email="taro@example.com").exists()
    assert not Visit.objects.exists() and not Stamp.objects.exists() and not Media.objects.exists()
    assert not (media_dir / str(taro.id)).exists()
    assert Place.objects.get(name_ja="小さな神社").created_by is None


def test_last_admin_cannot_delete_account(media_dir):
    admin = User.objects.create_superuser("admin@example.com", "pw-admin-12345")
    response = post(client_for(admin), "/api/me/delete", {"password": "pw-admin-12345"})
    assert response.status_code == 409
