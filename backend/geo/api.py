from typing import Optional

from ninja import Router, Schema

from .models import Area, Prefecture, Region

router = Router(tags=["geo"])


class RegionOut(Schema):
    id: int
    slug: str
    name_ja: str
    name_en: str
    name_es: str


class PrefectureOut(Schema):
    id: int
    iso_code: str
    region_id: int
    name_ja: str
    name_romaji: str
    name_en: str
    name_es: str
    lat: Optional[float] = None
    lon: Optional[float] = None


class AreaOut(Schema):
    id: int
    slug: str
    prefecture_id: int
    name_ja: Optional[str]
    name_en: str
    name_es: Optional[str]


@router.get("/regions", response=list[RegionOut])
def regions(request):
    return Region.objects.all()


@router.get("/prefectures", response=list[PrefectureOut])
def prefectures(request, region: Optional[int] = None):
    qs = Prefecture.objects.defer("boundary")
    if region is not None:
        qs = qs.filter(region_id=region)
    return [
        {
            "id": p.id,
            "iso_code": p.iso_code,
            "region_id": p.region_id,
            "name_ja": p.name_ja,
            "name_romaji": p.name_romaji,
            "name_en": p.name_en,
            "name_es": p.name_es,
            "lat": p.centroid.y if p.centroid else None,
            "lon": p.centroid.x if p.centroid else None,
        }
        for p in qs
    ]


@router.get("/areas", response=list[AreaOut])
def areas(request, prefecture: Optional[int] = None):
    qs = Area.objects.all()
    if prefecture is not None:
        qs = qs.filter(prefecture_id=prefecture)
    return qs
