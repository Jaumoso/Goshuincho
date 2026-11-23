import pytest

from accounts.models import User
from places.models import Place, PlaceCorrection
from places.services import CorrectionError, apply_correction, reject_correction

from .test_places_visits import kyoto, post, temple  # noqa: F401
from .test_portability import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def users():
    taro = User.objects.create_user("taro@example.com", "pw-taro-12345")
    admin = User.objects.create_superuser("admin@example.com", "pw-admin-12345")
    return taro, admin


def test_propose_and_apply_correction(temple, users):  # noqa: F811
    taro, admin = users
    temple.source, temple.osm_type, temple.osm_id = "osm", "way", 123
    temple.save()
    client = client_for(taro)
    url = f"/api/places/{temple.id}/corrections"

    # Sin cambios reales (mismo nombre) ni comentario → 422.
    assert post(client, url, {"changes": {"name_ja": "東寺"}}).status_code == 422
    assert post(client, url, {"changes": {"lat": 50, "lon": 135}}).status_code == 422

    response = post(client, url, {
        "changes": {"name_ja": "東寺", "name_en": "Tō-ji Temple", "website": "https://toji.or.jp", "lat": 34.98, "lon": 135.75},
        "comment": "Web oficial",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["changes"] == {"name_en": "Tō-ji Temple", "website": "https://toji.or.jp", "lat": 34.98, "lon": 135.75}
    assert client.get(url).json()[0]["status"] == "pending"

    correction = PlaceCorrection.objects.get()
    apply_correction(correction, admin)
    temple.refresh_from_db()
    assert (temple.name_en, temple.website, temple.locally_modified) == ("Tō-ji Temple", "https://toji.or.jp", True)
    assert (round(temple.location.y, 2), round(temple.location.x, 2)) == (34.98, 135.75)
    assert temple.prefecture_id == 26
    correction.refresh_from_db()
    assert (correction.status, correction.reviewed_by) == ("applied", admin)
    with pytest.raises(CorrectionError):
        apply_correction(correction, admin)


def test_reject_and_only_approved_places(temple, kyoto, users):  # noqa: F811
    taro, admin = users
    client = client_for(taro)
    post(client, f"/api/places/{temple.id}/corrections", {"changes": {}, "comment": "Cierra los lunes"})
    correction = PlaceCorrection.objects.get()
    assert correction.changes == {}
    assert reject_correction(correction, admin) == 1
    correction.refresh_from_db()
    assert correction.status == "rejected"

    own = Place.objects.create(kind="shrine", name_ja="小社", prefecture=kyoto, status="pending", created_by=taro)
    assert post(client, f"/api/places/{own.id}/corrections", {"changes": {"name_en": "X"}}).status_code == 409
