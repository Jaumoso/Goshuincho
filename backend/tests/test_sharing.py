from django.test import Client

import pytest

from accounts.models import User

from .test_places_visits import jpeg_bytes, kyoto, post, temple  # noqa: F401
from .test_portability import client_for, make_collection, media_dir  # noqa: F401

pytestmark = pytest.mark.django_db


def test_shared_collection_is_public_and_hides_private_fields(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345", display_name="Taro")
    client = client_for(taro)
    make_collection(client, kyoto, temple)
    link = post(client, "/api/share-links", {"title": "Mis goshuin"}).json()

    anon = Client()
    response = anon.get(f"/api/shared/{link['token']}")
    assert response.status_code == 200
    assert response["X-Robots-Tag"].startswith("noindex")
    data = response.json()
    assert (data["owner"], data["title"], data["count"], data["book"]) == ("Taro", "Mis goshuin", 1, None)
    stamp = data["items"][0]
    assert stamp["title"] == "Kōbō Daishi" and stamp["place"]["name_ja"] == "東寺"
    body = response.content.decode()
    assert "Pagoda" not in body and "taro@example.com" not in body and "donation" not in body

    media_id = stamp["media"][0]
    assert anon.get(f"/api/shared/{link['token']}/media/{media_id}/thumb").status_code == 200
    assert anon.get(f"/api/shared/{link['token']}/media/{media_id}/original").status_code == 422
    assert anon.get(f"/api/media/{media_id}/thumb").status_code == 401

    assert client.get("/api/share-links").json()[0]["view_count"] == 1
    assert client.delete(f"/api/share-links/{link['id']}").status_code == 204
    assert anon.get(f"/api/shared/{link['token']}").status_code == 404
    assert anon.get(f"/api/shared/{link['token']}/media/{media_id}/thumb").status_code == 404


def test_book_link_only_shows_that_book(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    client = client_for(taro)
    make_collection(client, kyoto, temple)
    other = post(client, "/api/goshuincho", {"name": "Segunda"}).json()
    post(client, f"/api/places/{temple.id}/visits", {
        "visited_on": "2024-05-01", "stamps": [{"kind": "goshuin", "goshuincho_id": other["id"]}],
    })
    assert client.get("/api/stamps").json()["count"] == 2

    link = post(client, "/api/share-links", {"goshuincho_id": other["id"]}).json()
    data = Client().get(f"/api/shared/{link['token']}").json()
    assert data["count"] == 1 and data["book"]["name"] == "Segunda"


def test_cannot_share_someone_elses_book_or_media(kyoto, temple, media_dir):  # noqa: F811
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    hanako = User.objects.create_user("hanako@example.com", "pw-hanako-12345")
    taro_client = client_for(taro)
    make_collection(taro_client, kyoto, temple)
    taro_book = taro_client.get("/api/goshuincho").json()[0]["id"]
    taro_media = taro_client.get("/api/stamps").json()["items"][0]["media"][0]["id"]

    hanako_client = client_for(hanako)
    assert post(hanako_client, "/api/share-links", {"goshuincho_id": taro_book}).status_code == 422
    link = post(hanako_client, "/api/share-links", {}).json()
    assert Client().get(f"/api/shared/{link['token']}/media/{taro_media}/thumb").status_code == 404
    assert hanako_client.delete(f"/api/share-links/{link['id']}").status_code == 204
    assert Client().get("/api/shared/no-existe").status_code == 404
