import re

from django.conf import settings
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseNotFound,
    HttpResponseNotModified,
    StreamingHttpResponse,
)
from django.views.decorators.http import require_http_methods


def spa(request):
    """Devuelve index.html de la PWA para cualquier ruta del cliente (React Router)."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        return HttpResponseNotFound("La PWA no está compilada (frontend/dist/index.html).")
    response = FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 64 * 1024


def _file_iter(path, start: int, length: int):
    with open(path, "rb") as fh:
        fh.seek(start)
        while length > 0:
            data = fh.read(min(CHUNK, length))
            if not data:
                break
            length -= len(data)
            yield data


@require_http_methods(["GET", "HEAD"])
def tiles(request, name: str):
    """Sirve los ficheros de ./tiles (PMTiles) con soporte de peticiones Range."""
    path = settings.TILES_DIR / name
    if "/" in name or name.startswith(".") or not path.is_file():
        raise Http404()
    stat = path.stat()
    size = stat.st_size
    etag = f'"{stat.st_mtime_ns:x}-{size:x}"'
    if request.headers.get("If-None-Match") == etag:
        return HttpResponseNotModified(headers={"ETag": etag})

    start, end, status = 0, size - 1, 200
    header = request.headers.get("Range")
    if_range = request.headers.get("If-Range")
    if header and (not if_range or if_range == etag):
        match = RANGE_RE.match(header.strip())
        if not match or match.groups() == ("", ""):
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            start = max(size - int(last), 0)
        if start > end or start >= size:
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        status = 206

    length = end - start + 1
    body = b"" if request.method == "HEAD" else _file_iter(path, start, length)
    response = StreamingHttpResponse(body, status=status, content_type="application/octet-stream")
    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    response["ETag"] = etag
    response["Cache-Control"] = "public, max-age=86400"
    if status == 206:
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    return response
