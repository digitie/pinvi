"""`/geo/*` + `/regions/*` — kor-travel-geo v2 REST geocoding/행정구역.

`docs/api/regions.md` + `docs/integrations/kor-travel-geo.md` (ADR-025). 좌표는 `(lon, lat)`,
대한민국 범위(ADR-018). kor-travel-geo client 미주입 시 503(GEOCODING_SERVICE_UNAVAILABLE).
"""

from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, HTTPException, Query, status

from app.clients.kor_travel_geo import (
    KorTravelGeoBadRequest,
    KorTravelGeoClientDep,
    KorTravelGeoUnavailable,
)
from app.core.deps import CurrentUserId
from app.schemas.envelope import Envelope
from app.schemas.geo import (
    BoundaryLevel,
    GeoCandidateList,
    RegionCovering,
    RegionsWithinRadius,
    RegionWithinRadiusItem,
    SearchKind,
)

geo_router = APIRouter(prefix="/geo", tags=["geo"])
regions_router = APIRouter(prefix="/regions", tags=["regions"])

LON = Query(ge=124.0, le=132.0, description="경도(대한민국 범위)")
LAT = Query(ge=33.0, le=43.0, description="위도(대한민국 범위)")


def _candidate_list(payload: dict[str, Any]) -> GeoCandidateList:
    return GeoCandidateList(
        status=str(payload.get("status", "ok")),
        candidates=[c for c in payload.get("candidates", []) if isinstance(c, dict)],
        total=payload.get("total") if isinstance(payload.get("total"), int) else None,
    )


def _raise_geo_http(exc: KorTravelGeoUnavailable | KorTravelGeoBadRequest) -> NoReturn:
    if isinstance(exc, KorTravelGeoUnavailable):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "GEOCODING_SERVICE_UNAVAILABLE",
                "message": "geocoding 서비스가 일시적으로 사용 불가합니다.",
            },
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": exc.code or "VALIDATION_ERROR", "message": str(exc)},
    ) from exc


@geo_router.get("/geocode", response_model=Envelope[GeoCandidateList])
async def geocode(
    _current_user: CurrentUserId,
    client: KorTravelGeoClientDep,
    query: Annotated[str, Query(min_length=1, max_length=200)],
    sig_cd: Annotated[str | None, Query(max_length=5)] = None,
    bjd_cd: Annotated[str | None, Query(max_length=10)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Envelope[GeoCandidateList]:
    """주소 → 좌표 후보."""
    try:
        payload = await client.geocode(query=query, sig_cd=sig_cd, bjd_cd=bjd_cd, limit=limit)
    except (KorTravelGeoUnavailable, KorTravelGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_candidate_list(payload))


@geo_router.get("/reverse", response_model=Envelope[GeoCandidateList])
async def reverse(
    _current_user: CurrentUserId,
    client: KorTravelGeoClientDep,
    lon: Annotated[float, LON],
    lat: Annotated[float, LAT],
    radius_m: Annotated[int, Query(ge=10, le=5000)] = 200,
) -> Envelope[GeoCandidateList]:
    """좌표 → 주소/행정구역 후보. 좌표 query는 location_audit 미들웨어가 chain 적재."""
    try:
        payload = await client.reverse(lon=lon, lat=lat, radius_m=radius_m)
    except (KorTravelGeoUnavailable, KorTravelGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_candidate_list(payload))


@geo_router.get("/search", response_model=Envelope[GeoCandidateList])
async def search(
    _current_user: CurrentUserId,
    client: KorTravelGeoClientDep,
    query: Annotated[str, Query(min_length=2, max_length=200)],
    type: Annotated[SearchKind, Query()] = "address",
    sig_cd: Annotated[str | None, Query(max_length=5)] = None,
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Envelope[GeoCandidateList]:
    """주소/도로명/행정구역/장소 검색(자동완성)."""
    try:
        payload = await client.search(query=query, kind=type, sig_cd=sig_cd, page=page, size=size)
    except (KorTravelGeoUnavailable, KorTravelGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_candidate_list(payload))


@regions_router.get("/covering-point", response_model=Envelope[RegionCovering])
async def regions_covering_point(
    _current_user: CurrentUserId,
    client: KorTravelGeoClientDep,
    lon: Annotated[float, LON],
    lat: Annotated[float, LAT],
    boundary_level: Annotated[BoundaryLevel, Query()] = "emd",
) -> Envelope[RegionCovering]:
    """좌표를 포함하는 행정구역(단건) — kor-travel-geo `/v2/reverse`의 최선 후보 region. 미매치 404.

    `boundary_level`은 응답에 echo되는 요청 hint다(reverse region에서 파생하지 않는다)."""
    try:
        payload = await client.reverse(lon=lon, lat=lat, include_region=True)
    except (KorTravelGeoUnavailable, KorTravelGeoBadRequest) as exc:
        _raise_geo_http(exc)
    region = _first_region(payload)
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "행정구역을 찾을 수 없습니다."},
        )
    return Envelope.of(RegionCovering(boundary_level=boundary_level, region=region))


def _first_region(payload: dict[str, Any]) -> dict[str, Any] | None:
    for candidate in payload.get("candidates", []):
        if isinstance(candidate, dict):
            region = candidate.get("region")
            if isinstance(region, dict) and region:
                return region
    return None


def _regions_within_radius(payload: dict[str, Any]) -> RegionsWithinRadius:
    def _items(level: str) -> list[RegionWithinRadiusItem]:
        items: list[RegionWithinRadiusItem] = []
        for raw in payload.get(level, []):
            if not isinstance(raw, dict):
                continue
            code = raw.get("code")
            relation = raw.get("relation")
            if not isinstance(code, str) or relation not in ("contains", "overlaps"):
                continue
            name = raw.get("name")
            items.append(
                RegionWithinRadiusItem(
                    code=code, name=name if isinstance(name, str) else None, relation=relation
                )
            )
        return items

    center = payload.get("center")
    radius_km = payload.get("radius_km")
    return RegionsWithinRadius(
        center=center if isinstance(center, dict) else {},
        radius_km=float(radius_km) if isinstance(radius_km, int | float) else 0.0,
        sido=_items("sido"),
        sigungu=_items("sigungu"),
        emd=_items("emd"),
    )


@regions_router.get("/within-radius", response_model=Envelope[RegionsWithinRadius])
async def regions_within_radius(
    _current_user: CurrentUserId,
    client: KorTravelGeoClientDep,
    lon: Annotated[float, LON],
    lat: Annotated[float, LAT],
    radius_km: Annotated[float, Query(gt=0, le=500.0)] = 3.0,
    levels: Annotated[list[BoundaryLevel] | None, Query()] = None,
) -> Envelope[RegionsWithinRadius]:
    """좌표 반경 내 행정구역 — level별(sido/sigungu/emd) 그룹. 기본 levels=[sigungu, emd]."""
    try:
        payload = await client.regions_within_radius(
            lon=lon, lat=lat, radius_km=radius_km, levels=levels or ["sigungu", "emd"]
        )
    except (KorTravelGeoUnavailable, KorTravelGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_regions_within_radius(payload))
