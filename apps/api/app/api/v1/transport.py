"""`/transport/*` — 지도 transport 레이어(주유소·휴게소·고속도로 돌발·공항), Map REST 경유 (ADR-076).

PinVi는 transport 데이터를 kor-travel-map `/v1/service/transport/*`로만 읽는다(Map ADR-114 결정 5). 설계
정본은 `docs/execplan/map-transport-integration.md`, 엔드포인트 계약은 `docs/api/transport.md`.

- `/transport/status`·`/transport/markers-in-bounds`는 **5xx를 내지 않는다** — Map 장애·적재 전은 레이어별
  상태로 강등한다(지도·여행 화면 보호).
- 상세·가격 추이는 사용자가 연 대화상자의 요청이라 404 `TRANSPORT_FEATURE_NOT_FOUND`·503
  `TRANSPORT_UNAVAILABLE`/`TRANSPORT_DISABLED`를 그대로 낸다.
- `PINVI_KOR_TRAVEL_MAP_TRANSPORT_ENABLED`가 꺼져 있으면(기본) Map을 부르지 않는다.
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.clients.kor_travel_map import (
    KorTravelMapClient,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    OptionalKorTravelMapHttpClientDep,
)
from app.core.bbox import MAX_ZOOM, MIN_ZOOM, parse_bbox
from app.core.config import settings
from app.core.deps import CurrentUserId
from app.core.time import kst_now
from app.schemas.envelope import Envelope
from app.schemas.transport import (
    TRANSPORT_LAYERS,
    FuelPriceHistoryResponse,
    TransportDetailResponse,
    TransportLayer,
    TransportLayerResult,
    TransportLayerStatus,
    TransportMarkersInBoundsResponse,
    TransportStatusResponse,
)
from app.services import transport_layers

router = APIRouter(prefix="/transport", tags=["transport"])

_DEFAULT_LIMIT = 200
#: Map `/v1/service/transport/*` `limit` 상한과 같다.
_MAX_LIMIT = 500
#: Map path `feature_id` 패턴(`^[A-Za-z0-9_\-]+$`, 1..128) — Map에 닿기 전에 막는다(경로 주입 차단).
_FEATURE_ID_PATTERN = r"^[A-Za-z0-9_\-]+$"

FeatureIdPath = Annotated[str, Path(min_length=1, max_length=128, pattern=_FEATURE_ID_PATTERN)]


def _unavailable(code: str = "TRANSPORT_UNAVAILABLE") -> HTTPException:
    message = (
        "교통 정보 기능이 꺼져 있습니다."
        if code == "TRANSPORT_DISABLED"
        else "교통 정보를 일시적으로 불러올 수 없습니다."
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": message},
    )


def _require_client(client: KorTravelMapClient | None) -> KorTravelMapClient:
    if not settings.pinvi_kor_travel_map_transport_enabled:
        raise _unavailable("TRANSPORT_DISABLED")
    if client is None:
        raise _unavailable()
    return client


def _raise_for(exc: KorTravelMapError) -> NoReturn:
    if isinstance(exc, KorTravelMapFeatureNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "TRANSPORT_FEATURE_NOT_FOUND",
                "message": "교통 정보 항목을 찾을 수 없습니다.",
            },
        ) from exc
    raise _unavailable() from exc


def _parse_layers(raw: list[str] | None) -> list[TransportLayer]:
    """`layers`(반복 또는 쉼표 구분) → 중복 없는 레이어 목록. 생략하면 전부."""
    if not raw:
        return list(TRANSPORT_LAYERS)
    wanted = {part.strip() for value in raw for part in value.split(",") if part.strip()}
    unknown = wanted - set(TRANSPORT_LAYERS)
    if unknown or not wanted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"layers는 {', '.join(TRANSPORT_LAYERS)} 중에서 고릅니다.",
            },
        )
    return [layer for layer in TRANSPORT_LAYERS if layer in wanted]


@router.get("/status", response_model=Envelope[TransportStatusResponse])
async def transport_status(
    _current_user: CurrentUserId,
    client: OptionalKorTravelMapHttpClientDep,
) -> Envelope[TransportStatusResponse]:
    """레이어 컨트롤 표시 여부·레이어별 가용성. 꺼져 있으면 ``enabled=false``(Map 미호출)."""
    if not settings.pinvi_kor_travel_map_transport_enabled:
        return Envelope.of(TransportStatusResponse(enabled=False))
    if client is None:
        return Envelope.of(
            TransportStatusResponse(
                enabled=True,
                layers=[
                    TransportLayerStatus(
                        layer=layer, available=False, reason="UPSTREAM_UNAVAILABLE"
                    )
                    for layer in TRANSPORT_LAYERS
                ],
            )
        )
    return Envelope.of(
        TransportStatusResponse(enabled=True, layers=await transport_layers.layer_status(client))
    )


@router.get("/markers-in-bounds", response_model=Envelope[TransportMarkersInBoundsResponse])
async def transport_markers_in_bounds(
    _current_user: CurrentUserId,
    client: OptionalKorTravelMapHttpClientDep,
    bbox: Annotated[str, Query(description="lng_min,lat_min,lng_max,lat_max")],
    zoom: Annotated[int, Query(ge=MIN_ZOOM, le=MAX_ZOOM)],
    layers: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> Envelope[TransportMarkersInBoundsResponse]:
    """viewport 안 transport 마커. 레이어마다 ``status``로 강등하고 5xx를 내지 않는다."""
    bbox_obj = parse_bbox(bbox)
    wanted = _parse_layers(layers)
    if not settings.pinvi_kor_travel_map_transport_enabled:
        results = transport_layers.disabled_layers(wanted)
    elif client is None:
        results = [
            TransportLayerResult(layer=layer, status="unavailable", reason="UPSTREAM_UNAVAILABLE")
            for layer in wanted
        ]
    else:
        results = await transport_layers.markers_in_bounds(
            client, bbox=bbox_obj.as_tuple(), layers=wanted, limit=limit
        )
    return Envelope.of(TransportMarkersInBoundsResponse(bbox=bbox_obj, zoom=zoom, layers=results))


async def _detail(
    client: KorTravelMapClient | None, layer: TransportLayer, feature_id: str
) -> Envelope[TransportDetailResponse]:
    resolved = _require_client(client)
    try:
        return Envelope.of(await transport_layers.detail(resolved, layer, feature_id))
    except KorTravelMapError as exc:
        _raise_for(exc)


@router.get("/fuel-stations/{feature_id}", response_model=Envelope[TransportDetailResponse])
async def fuel_station_detail(
    _current_user: CurrentUserId,
    client: OptionalKorTravelMapHttpClientDep,
    feature_id: FeatureIdPath,
) -> Envelope[TransportDetailResponse]:
    return await _detail(client, "fuel_station", feature_id)


@router.get("/rest-areas/{feature_id}", response_model=Envelope[TransportDetailResponse])
async def rest_area_detail(
    _current_user: CurrentUserId,
    client: OptionalKorTravelMapHttpClientDep,
    feature_id: FeatureIdPath,
) -> Envelope[TransportDetailResponse]:
    return await _detail(client, "rest_area", feature_id)


@router.get("/highway-incidents/{feature_id}", response_model=Envelope[TransportDetailResponse])
async def highway_incident_detail(
    _current_user: CurrentUserId,
    client: OptionalKorTravelMapHttpClientDep,
    feature_id: FeatureIdPath,
) -> Envelope[TransportDetailResponse]:
    return await _detail(client, "highway_incident", feature_id)


@router.get("/airports/{feature_id}", response_model=Envelope[TransportDetailResponse])
async def airport_detail(
    _current_user: CurrentUserId,
    client: OptionalKorTravelMapHttpClientDep,
    feature_id: FeatureIdPath,
) -> Envelope[TransportDetailResponse]:
    return await _detail(client, "airport", feature_id)


@router.get(
    "/fuel-stations/{feature_id}/price-history",
    response_model=Envelope[FuelPriceHistoryResponse],
)
async def fuel_station_price_history(
    _current_user: CurrentUserId,
    client: OptionalKorTravelMapHttpClientDep,
    feature_id: FeatureIdPath,
    product_key: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> Envelope[FuelPriceHistoryResponse]:
    """가격 추이. 추이가 없으면 200 + ``status=unavailable``(transport가 아직 내보내지 않음 등)."""
    resolved = _require_client(client)
    try:
        return Envelope.of(
            await transport_layers.fuel_price_history(
                resolved,
                feature_id,
                product_key=product_key,
                days=days,
                now=kst_now(),
            )
        )
    except KorTravelMapError as exc:
        _raise_for(exc)
