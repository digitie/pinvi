"""`/geo/*` + `/regions/*` — kraddr-geo v2 REST geocoding/행정구역.

`docs/api/regions.md` + `docs/integrations/kraddr-geo.md` (ADR-025). 좌표는 `(lon, lat)`,
대한민국 범위(ADR-018). kraddr-geo client 미주입 시 503(GEOCODING_SERVICE_UNAVAILABLE).
"""

from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, HTTPException, Query, status

from app.clients.kraddr_geo import (
    KraddrGeoBadRequest,
    KraddrGeoClientDep,
    KraddrGeoUnavailable,
)
from app.core.deps import CurrentUserId
from app.schemas.envelope import Envelope
from app.schemas.geo import BoundaryLevel, GeoCandidateList, RegionCovering, SearchKind

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


def _raise_geo_http(exc: KraddrGeoUnavailable | KraddrGeoBadRequest) -> NoReturn:
    if isinstance(exc, KraddrGeoUnavailable):
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
    client: KraddrGeoClientDep,
    query: Annotated[str, Query(min_length=1, max_length=200)],
    sig_cd: Annotated[str | None, Query(max_length=5)] = None,
    bjd_cd: Annotated[str | None, Query(max_length=10)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Envelope[GeoCandidateList]:
    """주소 → 좌표 후보."""
    try:
        payload = await client.geocode(query=query, sig_cd=sig_cd, bjd_cd=bjd_cd, limit=limit)
    except (KraddrGeoUnavailable, KraddrGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_candidate_list(payload))


@geo_router.get("/reverse", response_model=Envelope[GeoCandidateList])
async def reverse(
    _current_user: CurrentUserId,
    client: KraddrGeoClientDep,
    longitude: Annotated[float, LON],
    latitude: Annotated[float, LAT],
    radius_m: Annotated[int, Query(ge=10, le=5000)] = 200,
) -> Envelope[GeoCandidateList]:
    """좌표 → 주소/행정구역 후보. 좌표 query는 location_audit 미들웨어가 chain 적재."""
    try:
        payload = await client.reverse(lon=longitude, lat=latitude, radius_m=radius_m)
    except (KraddrGeoUnavailable, KraddrGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_candidate_list(payload))


@geo_router.get("/search", response_model=Envelope[GeoCandidateList])
async def search(
    _current_user: CurrentUserId,
    client: KraddrGeoClientDep,
    query: Annotated[str, Query(min_length=2, max_length=200)],
    type: Annotated[SearchKind, Query()] = "address",
    sig_cd: Annotated[str | None, Query(max_length=5)] = None,
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Envelope[GeoCandidateList]:
    """주소/도로명/행정구역/장소 검색(자동완성)."""
    try:
        payload = await client.search(query=query, kind=type, sig_cd=sig_cd, page=page, size=size)
    except (KraddrGeoUnavailable, KraddrGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_candidate_list(payload))


@regions_router.get("/covering-point", response_model=Envelope[RegionCovering])
async def regions_covering_point(
    _current_user: CurrentUserId,
    client: KraddrGeoClientDep,
    longitude: Annotated[float, LON],
    latitude: Annotated[float, LAT],
    boundary_level: Annotated[BoundaryLevel, Query()] = "legal_dong",
) -> Envelope[RegionCovering]:
    """좌표를 포함하는 행정구역(단건) — kraddr-geo `/v2/reverse`의 최선 후보 region. 미매치 404."""
    try:
        payload = await client.reverse(lon=longitude, lat=latitude, include_region=True)
    except (KraddrGeoUnavailable, KraddrGeoBadRequest) as exc:
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


@regions_router.get("/within-radius", response_model=Envelope[GeoCandidateList])
async def regions_within_radius(
    _current_user: CurrentUserId,
    client: KraddrGeoClientDep,
    longitude: Annotated[float, LON],
    latitude: Annotated[float, LAT],
    radius_m: Annotated[int, Query(ge=100, le=50000)] = 2000,
    boundary_level: Annotated[BoundaryLevel, Query()] = "legal_dong",
) -> Envelope[GeoCandidateList]:
    """좌표 반경 내 행정구역 후보 목록."""
    try:
        payload = await client.regions_within_radius(
            lon=longitude, lat=latitude, radius_m=radius_m, boundary_level=boundary_level
        )
    except (KraddrGeoUnavailable, KraddrGeoBadRequest) as exc:
        _raise_geo_http(exc)
    return Envelope.of(_candidate_list(payload))
