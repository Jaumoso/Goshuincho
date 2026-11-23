import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import Client, RequestFactory, override_settings

from accounts.models import User
from geo.models import Area, Prefecture, Region
from goshuincho.middleware import TrustedProxyMiddleware

pytestmark = pytest.mark.django_db

PASSWORD = "kitsune-inari-2024"


@pytest.fixture
def user():
    return User.objects.create_user("Taro@Example.com", PASSWORD, display_name="Taro")


@pytest.fixture
def client():
    return Client(enforce_csrf_checks=True)


def login(client, email, password):
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return client.post(
        "/api/auth/login",
        {"email": email, "password": password},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_me_logout(client, user):
    assert client.get("/api/me").status_code == 401

    response = login(client, "taro@example.com", PASSWORD)
    assert response.status_code == 200
    assert response.json()["email"] == "taro@example.com"

    me = client.get("/api/me").json()
    assert me["display_name"] == "Taro" and me["role"] == "user"

    token = client.cookies["csrftoken"].value
    assert client.post("/api/auth/logout", headers={"X-CSRFToken": token}).status_code == 204
    assert client.get("/api/me").status_code == 401


def test_login_requires_csrf(client, user):
    response = client.post(
        "/api/auth/login",
        {"email": "taro@example.com", "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 403


def test_login_wrong_password(client, user):
    assert login(client, "taro@example.com", "wrong").status_code == 401


def test_login_lockout(client, user):
    for _ in range(5):
        login(client, "taro@example.com", "wrong")
    assert login(client, "taro@example.com", PASSWORD).status_code == 429


def test_update_me_locale(client, user):
    login(client, "taro@example.com", PASSWORD)
    token = client.cookies["csrftoken"].value
    response = client.patch(
        "/api/me", {"locale": "en"}, content_type="application/json", headers={"X-CSRFToken": token}
    )
    assert response.status_code == 200 and response.json()["locale"] == "en"
    user.refresh_from_db()
    assert user.locale == "en"


def test_admin_role_grants_staff():
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    assert admin.is_staff and admin.is_superuser
    admin.role = User.Role.USER
    admin.save(update_fields=["role"])
    admin.refresh_from_db()
    assert not admin.is_staff and not admin.is_superuser


@override_settings(ADMIN_EMAIL="Boss@Example.com", ADMIN_PASSWORD=PASSWORD)
def test_seed():
    call_command("seed", "--if-empty")

    assert Region.objects.count() == 8
    assert Prefecture.objects.count() == 47
    assert Prefecture.objects.filter(boundary__isnull=True).count() == 0
    assert Area.objects.exists()
    assert Prefecture.objects.get(iso_code="JP-24").region.slug == "kansai"

    fushimi_inari = Point(135.7727, 34.9671, srid=4326)
    assert Prefecture.objects.get(boundary__contains=fushimi_inari).iso_code == "JP-26"
    senso_ji = Point(139.7967, 35.7148, srid=4326)
    assert Prefecture.objects.get(boundary__contains=senso_ji).name_es == "Tokio"

    admin = User.objects.get(email="boss@example.com")
    assert admin.is_staff

    call_command("seed", "--if-empty")
    assert Prefecture.objects.count() == 47
    assert User.objects.count() == 1


def test_reference_endpoints(client, user):
    call_command("seed")
    login(client, "taro@example.com", PASSWORD)
    assert len(client.get("/api/regions").json()) == 8
    kansai = client.get("/api/prefectures", {"region": 5}).json()
    assert {p["name_es"] for p in kansai} >= {"Kioto", "Nara", "Mie"}
    assert all(p["lat"] and p["lon"] for p in kansai)
    assert client.get("/api/areas", {"prefecture": 26}).json()


@override_settings(TRUSTED_PROXIES=["10.0.0.0/8"])
@pytest.mark.parametrize(
    "remote, expected_ip, expected_scheme",
    [("10.0.0.2", "203.0.113.7", "https"), ("198.51.100.1", "198.51.100.1", "http")],
)
def test_trusted_proxy(remote, expected_ip, expected_scheme):
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR=remote,
        HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7, 10.0.0.3",
        HTTP_X_FORWARDED_PROTO="https",
    )
    TrustedProxyMiddleware(lambda r: r)(request)
    assert request.META["REMOTE_ADDR"] == expected_ip
    assert request.scheme == expected_scheme
