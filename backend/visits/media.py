"""Almacenamiento de imágenes en el volumen local y generación de variantes."""

import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
    "HEIF": ("image/heic", "heic"),
}
VARIANTS = {"thumb": 320, "medium": 1280}
EXIF_IFD, GPS_IFD, DATETIME_ORIGINAL = 0x8769, 0x8825, 0x9003
TOKYO = ZoneInfo("Asia/Tokyo")


class InvalidImage(Exception):
    pass


class TooLarge(Exception):
    pass


def media_root() -> Path:
    return Path(settings.MEDIA_ROOT)


def save_upload(upload) -> tuple[Path, str, int]:
    """Copia la subida a un temporal calculando el SHA-256 y comprobando el tamaño."""
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    root = media_root()
    root.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in upload.chunks():
                size += len(chunk)
                if size > limit:
                    raise TooLarge()
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        os.unlink(tmp)
        raise
    return Path(tmp), digest.hexdigest(), size


def inspect(path: Path) -> dict:
    """Comprueba el tipo por contenido y extrae tamaño y fecha de la foto."""
    try:
        with Image.open(path) as img:
            fmt = img.format
            if fmt not in FORMATS:
                raise InvalidImage()
            img.verify()
        with Image.open(path) as img:
            width, height = ImageOps.exif_transpose(img).size
            exif = img.getexif()
    except InvalidImage:
        raise
    except Exception as exc:
        raise InvalidImage() from exc
    mime, ext = FORMATS[fmt]
    taken_at = None
    raw = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) if exif else None
    if isinstance(raw, str):
        try:
            taken_at = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S").replace(tzinfo=TOKYO)
        except ValueError:
            pass
    return {"mime": mime, "ext": ext, "width": width, "height": height, "taken_at": taken_at}


def strip_location(path: Path):
    """Quita la ubicación GPS del original cuando KEEP_ORIGINAL_EXIF está desactivado."""
    with Image.open(path) as img:
        exif = img.getexif()
        if GPS_IFD not in exif:
            return
        del exif[GPS_IFD]
        img.load()
        fmt = img.format
        kwargs = {"exif": exif.tobytes()}
        if fmt == "JPEG":
            kwargs.update(quality=95)
        img.save(path, format=fmt, **kwargs)


def storage_key(user_id, sha: str, ext: str) -> str:
    return f"{user_id}/{sha[:2]}/{sha}.{ext}"


def store(tmp: Path, key: str):
    dest = media_root() / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, dest)


def generate_variants(media) -> dict:
    """Genera las variantes WebP sin metadatos y devuelve el diccionario de claves."""
    src = media_root() / media.storage_key
    base = media.storage_key.rsplit(".", 1)[0]
    variants = dict(media.variants or {})
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        for name, size in VARIANTS.items():
            key = f"{base}_{name}.webp"
            copy = img.copy()
            copy.thumbnail((size, size), Image.Resampling.LANCZOS)
            dest = media_root() / key
            tmp = dest.with_suffix(".tmp")
            copy.save(tmp, format="WEBP", quality=82, method=4)
            os.replace(tmp, dest)
            variants[name] = key
    return variants


def ensure_variants(media):
    if all(media.variants.get(name) for name in VARIANTS) and all(
        (media_root() / media.variants[name]).exists() for name in VARIANTS
    ):
        return
    media.variants = generate_variants(media)
    media.save(update_fields=["variants"])


def delete_files(media):
    keys = [media.storage_key, *(media.variants or {}).values()]
    for key in keys:
        try:
            (media_root() / key).unlink()
        except FileNotFoundError:
            pass
