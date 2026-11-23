"""Lectura asistida de la inscripción de un goshuin: furigana, rōmaji y glosario, sin conexión."""

import re
import uuid
from typing import Optional

from ninja import Field, Router, Schema

from places.api import visible_place
from places.osm import LONG_VOWELS, _convert

router = Router(tags=["kanji"])

# (término, lectura, español, inglés). Los términos compuestos ganan a la lectura de pykakasi,
# que suele fallar con el vocabulario budista y sintoísta.
GLOSSARY: list[tuple[str, str, str, str]] = [
    ("奉拝", "ほうはい", "«visité con respeto»; encabeza casi todos los goshuin", "“respectfully visited”; heads most goshuin"),
    ("奉納", "ほうのう", "ofrenda", "offering"),
    ("参拝", "さんぱい", "visita de culto", "worship visit"),
    ("御朱印帳", "ごしゅいんちょう", "libreta de goshuin", "goshuin book"),
    ("御朱印", "ごしゅいん", "sello caligrafiado de templo o santuario", "temple or shrine seal"),
    ("御神印", "ごしんいん", "sello de santuario", "shrine seal"),
    ("御首題", "ごしゅだい", "goshuin de la escuela Nichiren", "Nichiren-school goshuin"),
    ("御宝印", "ごほういん", "sello del tesoro (sello del templo)", "treasure seal (temple seal)"),
    ("宝印", "ほういん", "sello del tesoro", "treasure seal"),
    ("梵字", "ぼんじ", "letra sánscrita (siddham) de la deidad", "Sanskrit (siddham) letter of the deity"),
    ("本尊", "ほんぞん", "imagen principal de culto", "principal image of worship"),
    ("本堂", "ほんどう", "sala principal", "main hall"),
    ("金堂", "こんどう", "sala dorada (sala principal)", "golden (main) hall"),
    ("社務所", "しゃむしょ", "oficina del santuario", "shrine office"),
    ("寺務所", "じむしょ", "oficina del templo", "temple office"),
    ("納経所", "のうきょうしょ", "oficina donde se dan los goshuin", "goshuin office"),
    ("霊場", "れいじょう", "lugar sagrado de peregrinación", "sacred pilgrimage site"),
    ("札所", "ふだしょ", "templo numerado de una ruta", "numbered pilgrimage temple"),
    ("八十八ヶ所", "はちじゅうはっかしょ", "88 lugares (ruta de Shikoku)", "88 places (Shikoku route)"),
    ("三十三所", "さんじゅうさんしょ", "33 lugares (rutas de Kannon)", "33 places (Kannon routes)"),
    ("西国", "さいごく", "Saigoku (oeste de Japón)", "Saigoku (western Japan)"),
    ("坂東", "ばんどう", "Bandō (Kantō)", "Bandō (Kantō)"),
    ("秩父", "ちちぶ", "Chichibu", "Chichibu"),
    ("四国", "しこく", "Shikoku", "Shikoku"),
    ("一宮", "いちのみや", "santuario principal de la provincia", "chief shrine of the province"),
    ("限定", "げんてい", "edición limitada", "limited edition"),
    ("吉日", "きちじつ", "día propicio (en lugar del día exacto)", "auspicious day (instead of exact date)"),
    ("令和", "れいわ", "era Reiwa (2019–)", "Reiwa era (2019–)"),
    ("平成", "へいせい", "era Heisei (1989–2019)", "Heisei era (1989–2019)"),
    ("昭和", "しょうわ", "era Shōwa (1926–1989)", "Shōwa era (1926–1989)"),
    ("南無妙法蓮華経", "なむみょうほうれんげきょう", "invocación al Sutra del Loto", "invocation of the Lotus Sutra"),
    ("南無大師遍照金剛", "なむだいしへんじょうこんごう", "invocación a Kōbō Daishi", "invocation of Kōbō Daishi"),
    ("遍照金剛", "へんじょうこんごう", "nombre sagrado de Kōbō Daishi", "sacred name of Kōbō Daishi"),
    ("弘法大師", "こうぼうだいし", "Kōbō Daishi (Kūkai)", "Kōbō Daishi (Kūkai)"),
    ("大師", "だいし", "gran maestro (normalmente Kūkai)", "great teacher (usually Kūkai)"),
    ("南無", "なむ", "«me refugio en…»", "“I take refuge in…”"),
    ("十一面観世音", "じゅういちめんかんぜおん", "Kannon de once caras", "eleven-headed Kannon"),
    ("千手観世音", "せんじゅかんぜおん", "Kannon de mil brazos", "thousand-armed Kannon"),
    ("聖観世音", "しょうかんぜおん", "Kannon sagrado", "holy Kannon"),
    ("如意輪観世音", "にょいりんかんぜおん", "Kannon de la joya y la rueda", "wish-fulfilling Kannon"),
    ("観世音", "かんぜおん", "Kannon, bodhisattva de la compasión", "Kannon, bodhisattva of compassion"),
    ("観音", "かんのん", "Kannon, bodhisattva de la compasión", "Kannon, bodhisattva of compassion"),
    ("大悲殿", "だいひでん", "sala de la gran compasión (de Kannon)", "hall of great compassion (Kannon)"),
    ("大日如来", "だいにちにょらい", "Buda Dainichi (Vairocana)", "Dainichi Buddha (Vairocana)"),
    ("薬師如来", "やくしにょらい", "Buda de la medicina", "Medicine Buddha"),
    ("阿弥陀如来", "あみだにょらい", "Buda Amida", "Amida Buddha"),
    ("釈迦如来", "しゃかにょらい", "Buda Shaka (histórico)", "Shaka (historical) Buddha"),
    ("如来", "にょらい", "buda", "buddha"),
    ("不動明王", "ふどうみょうおう", "Fudō Myōō, rey de sabiduría", "Fudō Myōō, wisdom king"),
    ("地蔵菩薩", "じぞうぼさつ", "Jizō, protector de niños y viajeros", "Jizō, protector of children and travellers"),
    ("地蔵", "じぞう", "Jizō", "Jizō"),
    ("菩薩", "ぼさつ", "bodhisattva", "bodhisattva"),
    ("毘沙門天", "びしゃもんてん", "Bishamonten, guardián", "Bishamonten, guardian deity"),
    ("弁財天", "べんざいてん", "Benzaiten, diosa de las artes", "Benzaiten, goddess of the arts"),
    ("大黒天", "だいこくてん", "Daikokuten, dios de la prosperidad", "Daikokuten, god of prosperity"),
    ("七福神", "しちふくじん", "los siete dioses de la fortuna", "the Seven Lucky Gods"),
    ("天照大御神", "あまてらすおおみかみ", "Amaterasu, diosa del sol", "Amaterasu, sun goddess"),
    ("八幡宮", "はちまんぐう", "santuario de Hachiman", "Hachiman shrine"),
    ("八幡", "はちまん", "Hachiman, dios de los guerreros", "Hachiman, god of warriors"),
    ("天満宮", "てんまんぐう", "santuario de Tenjin (Sugawara no Michizane)", "Tenjin shrine (Sugawara no Michizane)"),
    ("稲荷", "いなり", "Inari, kami del arroz y la prosperidad", "Inari, kami of rice and prosperity"),
    ("神宮", "じんぐう", "gran santuario (vinculado a la casa imperial)", "grand shrine (imperial link)"),
    ("大社", "たいしゃ", "gran santuario", "grand shrine"),
    ("神社", "じんじゃ", "santuario sintoísta", "Shinto shrine"),
    ("大神", "おおかみ", "gran kami", "great kami"),
    ("鎮守", "ちんじゅ", "kami protector del lugar", "local guardian kami"),
    ("宮司", "ぐうじ", "sumo sacerdote del santuario", "chief priest"),
    ("住職", "じゅうしょく", "monje a cargo del templo", "head priest of the temple"),
    ("山", "さん", "monte (nombre de montaña del templo, sangō)", "mountain (temple's mountain name)"),
    ("寺", "じ", "templo budista", "Buddhist temple"),
    ("院", "いん", "templo o subtemplo", "temple or sub-temple"),
    ("堂", "どう", "sala", "hall"),
    ("宮", "ぐう", "santuario", "shrine"),
    ("社", "しゃ", "santuario", "shrine"),
    ("第", "だい", "número… (ordinal)", "number… (ordinal)"),
    ("番", "ばん", "número (en una ruta)", "number (on a route)"),
]
# Los términos de un carácter solo se glosan si pykakasi los deja sueltos (東寺 se lee entero).
_BY_LENGTH = sorted((g for g in GLOSSARY if len(g[0]) > 1), key=lambda g: -len(g[0]))
_LOOKUP = {g[0]: g for g in GLOSSARY}

COMMON = {
    "temple": ["奉拝", "本尊", "南無", "観世音", "大師", "霊場", "札所", "第", "番", "令和", "年", "月", "日", "吉日"],
    "shrine": ["奉拝", "神社", "大社", "神宮", "八幡宮", "天満宮", "稲荷", "一宮", "令和", "年", "月", "日", "吉日"],
}
COMMON["station"] = ["令和", "年", "月", "日", "駅"]
COMMON["site"] = COMMON["temple"]

JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff々〆ヶ]")
KANJI = re.compile(r"[\u3400-\u9fff\uf900-\ufaff々〆ヶ]")


def _romaji(kana: str) -> str:
    out = "".join(item["hepburn"] for item in _convert(kana))
    for long, macron in LONG_VOWELS:
        out = out.replace(long, macron)
    return out


def _token(text: str, kana: Optional[str], gloss=None) -> dict:
    romaji = _romaji(kana or text) if JAPANESE.search(text) else text
    return {
        "text": text,
        # Sin furigana cuando no hay kanji: la lectura ya está a la vista.
        "kana": kana if kana and KANJI.search(text) and kana != text else None,
        "romaji": romaji,
        "gloss_es": gloss[2] if gloss else None,
        "gloss_en": gloss[3] if gloss else None,
    }


def read(text: str) -> list[dict]:
    """Trocea el texto: primero el glosario (coincidencia más larga) y el resto con pykakasi."""
    tokens, plain, i = [], "", 0

    def flush():
        nonlocal plain
        if plain:
            prev = ""
            for item in _convert(plain):
                orig, kana = item["orig"], item["hira"]
                gloss = _LOOKUP.get(orig)
                if gloss and KANJI.search(prev[-1:]):
                    kana = gloss[1]  # Sufijo pegado a un nombre: 立江寺 → たつえじ, no たつえてら.
                if orig.strip():
                    tokens.append(_token(orig, kana, gloss))
                prev = orig
            plain = ""

    while i < len(text):
        match = next((g for g in _BY_LENGTH if text.startswith(g[0], i)), None)
        if match:
            flush()
            tokens.append(_token(match[0], match[1], match))
            i += len(match[0])
        else:
            plain += text[i]
            i += 1
    flush()
    return tokens


class Token(Schema):
    text: str
    kana: Optional[str]
    romaji: str
    gloss_es: Optional[str]
    gloss_en: Optional[str]


class ReadIn(Schema):
    text: str = Field(..., max_length=500)


class Reading(Schema):
    tokens: list[Token]
    romaji: str


class Hint(Schema):
    text: str
    kana: Optional[str]
    romaji: str
    gloss_es: Optional[str]
    gloss_en: Optional[str]


def reading(text: str) -> dict:
    tokens = read(text.strip())
    return {"tokens": tokens, "romaji": " ".join(t["romaji"] for t in tokens if t["romaji"].strip())}


@router.post("/kanji/read", response=Reading)
def read_text(request, payload: ReadIn):
    return reading(payload.text)


def _hint(text: str) -> dict:
    if text in _LOOKUP:
        return _token(text, _LOOKUP[text][1], _LOOKUP[text])
    tokens = read(text)
    kana = "".join(t["kana"] or t["text"] for t in tokens)
    return {**_token(text, kana), "romaji": "".join(t["romaji"] for t in tokens)}


@router.get("/kanji/hints", response=list[Hint])
def hints(request, place_id: Optional[uuid.UUID] = None):
    """Piezas para componer la inscripción: nombres del lugar y vocabulario habitual."""
    texts, kind = [], "temple"
    if place_id:
        place = visible_place(request.user, place_id)
        kind = place.kind
        names = [place.name_ja, *(place.alt_names or [])]
        texts += [n.strip() for n in names if n and KANJI.search(n)]
    texts += COMMON[kind]
    seen = set()
    return [_hint(t) for t in texts if not (t in seen or seen.add(t))]
