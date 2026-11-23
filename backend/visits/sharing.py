"""Colecciones compartidas por enlace de solo lectura (RF-15).

El token es el único secreto: quien lo tiene ve los goshuin incluidos (fotos, lugar, fecha, tipo y
título), pero nunca notas, donativos ni el email del usuario. Borrar el enlace lo revoca.
"""

import uuid
from datetime import date, datetime
from typing import Literal, Optional

from django.db.models import F
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from . import media as storage
from .api import PAGE_MAX, check_goshuincho, place_ref, stamp_queryset
from .models import Media, ShareLink, StampMedia

router = Router(tags=["sharing"])
public = Router(tags=["sharing"], auth=None)


class ShareLinkIn(Schema):
    goshuincho_id: Optional[uuid.UUID] = None
    title: Optional[str] = Field(None, max_length=200)


class ShareLinkOut(Schema):
    id: uuid.UUID
    token: str
    goshuincho_id: Optional[uuid.UUID]
    goshuincho_name: Optional[str]
    title: Optional[str]
    created_at: datetime
    last_viewed_at: Optional[datetime]
    view_count: int


class SharedPlace(Schema):
    kind: str
    name_ja: Optional[str]
    name_romaji: Optional[str]
    name_en: Optional[str]
    prefecture_id: int


class SharedStamp(Schema):
    id: uuid.UUID
    kind: str
    medium: Optional[str]
    title: Optional[str]
    event_name: Optional[str]
    place: SharedPlace
    visited_on: Optional[date]
    visited_precision: str
    media: list[uuid.UUID]


class SharedBook(Schema):
    name: str
    description: Optional[str]
    started_on: Optional[date]
    finished_on: Optional[date]


class SharedCollection(Schema):
    title: Optional[str]
    owner: str
    book: Optional[SharedBook]
    count: int
    place_count: int
    items: list[SharedStamp]
    next_offset: Optional[int]


def link_out(link: ShareLink) -> dict:
    return {
        "id": link.id,
        "token": link.token,
        "goshuincho_id": link.goshuincho_id,
        "goshuincho_name": link.goshuincho.name if link.goshuincho else None,
        "title": link.title,
        "created_at": link.created_at,
        "last_viewed_at": link.last_viewed_at,
        "view_count": link.view_count,
    }


@router.get("/share-links", response=list[ShareLinkOut])
def list_links(request):
    links = ShareLink.objects.filter(user=request.user).select_related("goshuincho").order_by("-created_at")
    return [link_out(link) for link in links]


@router.post("/share-links", response={201: ShareLinkOut})
def create_link(request, payload: ShareLinkIn):
    check_goshuincho(request.user, payload.goshuincho_id)
    link = ShareLink.objects.create(
        user=request.user, goshuincho_id=payload.goshuincho_id, title=(payload.title or "").strip() or None
    )
    return Status(201, link_out(link))


@router.delete("/share-links/{link_id}", response={204: None})
def delete_link(request, link_id: uuid.UUID):
    get_object_or_404(ShareLink, id=link_id, user=request.user).delete()
    return Status(204, None)


def shared_stamps(link: ShareLink):
    qs = stamp_queryset(link.user_id)
    if link.goshuincho_id:
        qs = qs.filter(goshuincho_id=link.goshuincho_id)
    return qs


def get_link(token: str) -> ShareLink:
    link = ShareLink.objects.select_related("user", "goshuincho").filter(token=token).first()
    if not link or not link.user.is_active:
        raise HttpError(404, "Not Found")
    return link


def private_headers(response):
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response


@public.get("/shared/{token}", response=SharedCollection)
def shared_collection(request, response: HttpResponse, token: str, offset: int = 0, limit: int = 48):
    link = get_link(token)
    private_headers(response)
    qs = shared_stamps(link)
    limit = max(1, min(limit, PAGE_MAX))
    offset = max(0, offset)
    if offset == 0:
        ShareLink.objects.filter(id=link.id).update(last_viewed_at=timezone.now(), view_count=F("view_count") + 1)
    count = qs.count()
    page = qs.order_by(F("visit__visited_on").desc(nulls_last=True), "-created_at")[offset : offset + limit]
    book = link.goshuincho
    return {
        "title": link.title,
        "owner": link.user.display_name,
        "book": (
            {
                "name": book.name,
                "description": book.description,
                "started_on": book.started_on,
                "finished_on": book.finished_on,
            }
            if book
            else None
        ),
        "count": count,
        "place_count": qs.values("place_id").distinct().count(),
        "items": [
            {
                "id": s.id,
                "kind": s.kind,
                "medium": s.medium,
                "title": s.title,
                "event_name": s.event_name,
                "place": place_ref(s.place),
                "visited_on": s.visit.visited_on,
                "visited_precision": s.visit.visited_precision,
                "media": [m.media_id for m in sorted(s.stampmedia_set.all(), key=lambda m: m.position)],
            }
            for s in page
        ],
        "next_offset": offset + limit if offset + limit < count else None,
    }


@public.get("/shared/{token}/media/{media_id}/{variant}")
def shared_media(request, token: str, media_id: uuid.UUID, variant: Literal["thumb", "medium"]):
    link = get_link(token)
    if not StampMedia.objects.filter(media_id=media_id, stamp__in=shared_stamps(link)).exists():
        raise HttpError(404, "Not Found")
    item = get_object_or_404(Media, id=media_id, user_id=link.user_id)
    storage.ensure_variants(item)
    path = storage.media_root() / item.variants[variant]
    if not path.exists():
        raise HttpError(404, "Not Found")
    response = FileResponse(open(path, "rb"), content_type="image/webp")
    # Sin caché compartida: revocar el enlace debe cortar el acceso.
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return private_headers(response)



