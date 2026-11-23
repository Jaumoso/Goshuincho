import pytest

from accounts.models import User

from .test_places_visits import kyoto, post, temple  # noqa: F401
from .test_portability import client_for

pytestmark = pytest.mark.django_db


def test_read_uses_glossary_and_suffix_readings():
    client = client_for(User.objects.create_user("taro@example.com", "pw-taro-12345"))
    data = post(client, "/api/kanji/read", {"text": "奉拝 第十九番 立江寺 令和六年"}).json()
    tokens = {t["text"]: t for t in data["tokens"]}
    assert tokens["奉拝"]["kana"] == "ほうはい" and tokens["奉拝"]["gloss_en"]
    assert tokens["寺"]["kana"] == "じ"
    assert data["romaji"].startswith("hōhai dai")


def test_hints_start_with_place_names(temple):  # noqa: F811
    client = client_for(User.objects.create_user("taro@example.com", "pw-taro-12345"))
    hints = client.get(f"/api/kanji/hints?place_id={temple.id}").json()
    assert hints[0] == {"text": "東寺", "kana": "とうじ", "romaji": "tōji", "gloss_es": None, "gloss_en": None}
    assert "奉拝" in [h["text"] for h in hints]


def test_stamp_inscription_is_saved_and_editable(temple):  # noqa: F811
    client = client_for(User.objects.create_user("taro@example.com", "pw-taro-12345"))
    post(client, f"/api/places/{temple.id}/visits", {
        "visited_on": "2024-05-01", "stamps": [{"kind": "goshuin", "inscription": "  奉拝 東寺 "}],
    })
    stamp = client.get("/api/stamps").json()["items"][0]
    assert stamp["inscription"] == "奉拝 東寺"
    response = client.patch(f"/api/stamps/{stamp['id']}", {"inscription": "奉拝 弘法大師"}, content_type="application/json")
    assert response.json()["inscription"] == "奉拝 弘法大師"
