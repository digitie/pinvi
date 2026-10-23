"""Map transport 상태 → PinVi 지도 레이어 (ADR-076).

Map `/v1/service/transport/*`를 PinVi 응답 schema로 투영한다. 지도·여행 화면이 깨지지 않도록 viewport
조회와 상태 조회는 **레이어별로 강등**한다 — 한 레이어의 Map 오류는 그 레이어의 ``status``가 될 뿐 HTTP
오류가 아니다. 상세·가격 추이는 사용자가 연 대화상자 안의 요청이라 오류를 그대로 올린다(라우터가 404/503).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final, cast

from pydantic import TypeAdapter, ValidationError

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapContractError,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
)
from app.clients.kor_travel_map_transport import (
    KorTravelMapTransportClient,
    KorTravelMapTransportCursorExpired,
    KorTravelMapTransportUnavailable,
    TransportDatasetPath,
)
from app.schemas.transport import (
    PRICE_HISTORY_REASONS,
    TRANSPORT_LAYERS,
    FuelPrice,
    FuelPriceHistoryPoint,
    FuelPriceHistoryResponse,
    PriceHistoryUnavailableReason,
    TransportDetailResponse,
    TransportFreshness,
    TransportItem,
    TransportLayer,
    TransportLayerResult,
    TransportLayerStatus,
    TransportUnavailableReason,
)

logger = logging.getLogger(__name__)

LAYER_DATASET_PATH: Final[dict[TransportLayer, TransportDatasetPath]] = {
    "fuel_station": "fuel-stations",
    "rest_area": "rest-areas",
    "highway_incident": "highway-incidents",
    "airport": "airports",
}

#: Map `TransportDatasetStatus.dataset` 이름(Map `kor_travel_transport_state.py`).
LAYER_MAP_DATASET: Final[dict[TransportLayer, str]] = {
    "fuel_station": "transport.fuel_stations",
    "rest_area": "transport.rest_areas",
    "highway_incident": "transport.highway_incidents",
    "airport": "transport.airports",
}

#: 국내 서비스 범위. viewport를 이 사각형과 교차해 Map에 보낸다 — 넓은 화면의 저배율 viewport가
#: Map의 영역 한 변 1,000 km 상한(422)에 걸리지 않게 한다(남북 약 670 km, 동서 약 710 km).
KOREA_TRANSPORT_BOUNDS: Final[tuple[float, float, float, float]] = (124.0, 33.0, 132.0, 39.0)

_ITEM_ADAPTER: Final[TypeAdapter[TransportItem]] = TypeAdapter(TransportItem)
_FRESHNESS_ADAPTER: Final[TypeAdapter[TransportFreshness]] = TypeAdapter(TransportFreshness)

_UPSTREAM_CODE_REASON: Final[dict[str, TransportUnavailableReason]] = {
    "TRANSPORT_STATE_NOT_LOADED": "NOT_LOADED",
    "TRANSPORT_STATE_UNAVAILABLE": "STORE_UNAVAILABLE",
    "UPSTREAM_AUTH": "UPSTREAM_AUTH",
}


class TransportContractError(KorTravelMapContractError):
    """Map 응답이 PinVi가 소비하는 필드 계약을 어겼다."""


#: 마커·상태 요청에서 레이어 하나가 응답을 붙잡을 수 있는 상한(초). 넘기면 그 레이어만 강등한다.
LAYER_DEADLINE_SECONDS: Final[float] = 3.0


def unavailable_reason(exc: KorTravelMapError | TimeoutError) -> TransportUnavailableReason:
    """client 예외 → 레이어 강등 사유."""
    if isinstance(exc, KorTravelMapTransportUnavailable):
        return _UPSTREAM_CODE_REASON.get(exc.code or "", "UPSTREAM_UNAVAILABLE")
    if isinstance(exc, KorTravelMapContractError):
        return "UPSTREAM_CONTRACT"
    if isinstance(
        exc,
        KorTravelMapFeatureNotFound | KorTravelMapBadRequest | KorTravelMapTransportCursorExpired,
    ):
        # 목록·상태에서 4xx는 Map 미배포(404)·검증 차이(422) 같은 계약 어긋남이다.
        return "UPSTREAM_REJECTED"
    return "UPSTREAM_UNAVAILABLE"


def clip_to_korea(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    """viewport ∩ 국내 범위. 교차가 없으면 ``None``."""
    min_lon = max(bbox[0], KOREA_TRANSPORT_BOUNDS[0])
    min_lat = max(bbox[1], KOREA_TRANSPORT_BOUNDS[1])
    max_lon = min(bbox[2], KOREA_TRANSPORT_BOUNDS[2])
    max_lat = min(bbox[3], KOREA_TRANSPORT_BOUNDS[3])
    if min_lon > max_lon or min_lat > max_lat:
        return None
    return (min_lon, min_lat, max_lon, max_lat)


def _parse[T](adapter: TypeAdapter[T], raw: object, what: str) -> T:
    try:
        return adapter.validate_python(raw)
    except ValidationError as exc:
        raise TransportContractError(
            f"Map transport {what} 셰입이 올바르지 않습니다: {exc}"
        ) from exc


def _item(layer: TransportLayer, raw: object) -> TransportItem:
    if not isinstance(raw, Mapping):
        raise TransportContractError("Map transport item이 객체가 아닙니다.")
    # discriminator는 PinVi가 붙인다 — Map 응답에는 layer가 없다(kind는 place/notice라 구분이 안 된다).
    return _parse(_ITEM_ADAPTER, {**raw, "layer": layer}, f"{layer} item")


def _items(layer: TransportLayer, raw_items: list[object]) -> list[TransportItem]:
    """목록 해석. 계약을 어긴 항목 하나가 레이어 전체를 지우지 않게 그 항목만 건너뛴다."""
    items: list[TransportItem] = []
    skipped = 0
    for raw in raw_items:
        try:
            items.append(_item(layer, raw))
        except TransportContractError:
            skipped += 1
    if skipped:
        logger.warning("transport.items_skipped", extra={"layer": layer, "skipped": skipped})
    return items


def _freshness(raw: object, what: str) -> TransportFreshness:
    return _parse(_FRESHNESS_ADAPTER, raw, what)


def _optional_freshness(raw: object, what: str) -> TransportFreshness | None:
    return None if raw is None else _freshness(raw, what)


async def _layer_in_bounds(
    client: KorTravelMapTransportClient,
    layer: TransportLayer,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> TransportLayerResult:
    if bbox is None:
        return TransportLayerResult(layer=layer, status="ok")
    try:
        data = await asyncio.wait_for(
            client.list_items(LAYER_DATASET_PATH[layer], bbox=bbox, limit=limit),
            timeout=LAYER_DEADLINE_SECONDS,
        )
        raw_items = data.get("items")
        truncated = data.get("truncated")
        if not isinstance(raw_items, list) or not isinstance(truncated, bool):
            raise TransportContractError(f"Map transport {layer} 목록 셰입이 올바르지 않습니다.")
        return TransportLayerResult(
            layer=layer,
            status="ok",
            freshness=_freshness(data.get("freshness"), f"{layer} freshness"),
            fuel_price_freshness=(
                _optional_freshness(data.get("fuel_price_freshness"), "fuel_price_freshness")
                if layer == "rest_area"
                else None
            ),
            truncated=truncated,
            items=_items(layer, raw_items),
        )
    except (KorTravelMapError, TimeoutError) as exc:
        reason = unavailable_reason(exc)
        logger.warning(
            "transport.layer_unavailable",
            extra={"layer": layer, "reason": reason, "error": type(exc).__name__},
        )
        return TransportLayerResult(layer=layer, status="unavailable", reason=reason)


async def markers_in_bounds(
    client: KorTravelMapTransportClient,
    *,
    bbox: tuple[float, float, float, float],
    layers: Sequence[TransportLayer],
    limit: int,
) -> list[TransportLayerResult]:
    """레이어별 viewport 결과. 레이어는 병렬로 부르고 각각 독립으로 강등한다."""
    clipped = clip_to_korea(bbox)
    return list(
        await asyncio.gather(*(_layer_in_bounds(client, layer, clipped, limit) for layer in layers))
    )


def disabled_layers(layers: Sequence[TransportLayer]) -> list[TransportLayerResult]:
    return [TransportLayerResult(layer=layer, status="disabled") for layer in layers]


async def layer_status(client: KorTravelMapTransportClient) -> list[TransportLayerStatus]:
    """Map `/status` → 레이어별 가용성. Map 전체 장애도 레이어별 ``available=false``로 강등한다."""
    try:
        data = await asyncio.wait_for(client.status(), timeout=LAYER_DEADLINE_SECONDS)
        raw_datasets = data.get("datasets")
        if not isinstance(raw_datasets, list):
            raise TransportContractError("Map transport status datasets가 목록이 아닙니다.")
        by_name: dict[str, Mapping[str, Any]] = {}
        for raw in raw_datasets:
            if not isinstance(raw, Mapping) or not isinstance(raw.get("dataset"), str):
                raise TransportContractError(
                    "Map transport status dataset 셰입이 올바르지 않습니다."
                )
            by_name[raw["dataset"]] = raw
        statuses: list[TransportLayerStatus] = []
        for layer in TRANSPORT_LAYERS:
            raw_status = by_name.get(LAYER_MAP_DATASET[layer])
            if raw_status is None:
                statuses.append(
                    TransportLayerStatus(layer=layer, available=False, reason="UPSTREAM_CONTRACT")
                )
            elif raw_status.get("loaded") is True:
                try:
                    fresh = _freshness(raw_status.get("freshness"), f"{layer} freshness")
                except TransportContractError:
                    # 이 데이터셋만 강등한다 — 나머지 레이어 상태는 그대로 보인다.
                    statuses.append(
                        TransportLayerStatus(
                            layer=layer, available=False, reason="UPSTREAM_CONTRACT"
                        )
                    )
                else:
                    statuses.append(
                        TransportLayerStatus(layer=layer, available=True, freshness=fresh)
                    )
            else:
                statuses.append(
                    TransportLayerStatus(
                        layer=layer,
                        available=False,
                        # error가 있으면 그 데이터셋만 읽지 못한 것이다(나머지는 정상).
                        reason=(
                            "STORE_UNAVAILABLE"
                            if raw_status.get("error") is not None
                            else "NOT_LOADED"
                        ),
                    )
                )
        return statuses
    except (KorTravelMapError, TimeoutError) as exc:
        reason = unavailable_reason(exc)
        logger.warning("transport.status_unavailable", extra={"reason": reason})
        return [
            TransportLayerStatus(layer=layer, available=False, reason=reason)
            for layer in TRANSPORT_LAYERS
        ]


async def detail(
    client: KorTravelMapTransportClient, layer: TransportLayer, feature_id: str
) -> TransportDetailResponse:
    """단건. Map 오류는 그대로 올린다(라우터가 404/503으로 바꾼다)."""
    data = await client.detail(LAYER_DATASET_PATH[layer], feature_id)
    item = _item(layer, data.get("item"))
    if item.feature_id != feature_id:
        raise TransportContractError("Map transport 상세 feature_id가 요청과 다릅니다.")
    return TransportDetailResponse(
        item=item,
        freshness=_freshness(data.get("freshness"), f"{layer} freshness"),
        fuel_price_freshness=(
            _optional_freshness(data.get("fuel_price_freshness"), "fuel_price_freshness")
            if layer == "rest_area"
            else None
        ),
    )


_HISTORY_POINTS_ADAPTER: Final[TypeAdapter[list[FuelPriceHistoryPoint]]] = TypeAdapter(
    list[FuelPriceHistoryPoint]
)
_PRICES_ADAPTER: Final[TypeAdapter[list[FuelPrice]]] = TypeAdapter(list[FuelPrice])


async def fuel_price_history(
    client: KorTravelMapTransportClient,
    feature_id: str,
    *,
    product_key: str | None,
    days: int,
    now: datetime,
) -> FuelPriceHistoryResponse:
    """주유소 가격 추이. 추이가 없으면 ``status=unavailable``(오류 아님)."""
    data = await client.fuel_price_history(feature_id, since=now - timedelta(days=days))
    history = data.get("history")
    if not isinstance(history, Mapping) or history.get("status") not in (
        "available",
        "unavailable",
    ):
        raise TransportContractError("Map 가격 추이 history 셰입이 올바르지 않습니다.")
    if data.get("feature_id") != feature_id:
        raise TransportContractError("Map 가격 추이 feature_id가 요청과 다릅니다.")
    raw_reason = history.get("reason")
    truncated = history.get("truncated")
    if not (raw_reason is None or isinstance(raw_reason, str)) or not isinstance(truncated, bool):
        raise TransportContractError("Map 가격 추이 history 셰입이 올바르지 않습니다.")
    # Map 원문은 넘기지 않는다 — 아는 enum만, 모르면 upstream_contract.
    reason: PriceHistoryUnavailableReason | None = None
    if raw_reason is not None:
        reason = (
            cast(PriceHistoryUnavailableReason, raw_reason)
            if raw_reason in PRICE_HISTORY_REASONS
            else "upstream_contract"
        )
    points = _parse(_HISTORY_POINTS_ADAPTER, history.get("items"), "가격 추이 items")
    current = _parse(_PRICES_ADAPTER, data.get("current_prices"), "current_prices")
    if product_key is not None:
        points = [point for point in points if point.product_key == product_key]
        current = [price for price in current if price.product_key == product_key]
    return FuelPriceHistoryResponse(
        feature_id=feature_id,
        status=history["status"],
        reason=reason,
        truncated=truncated,
        items=points,
        current_prices=current,
        freshness=_freshness(data.get("freshness"), "fuel_station freshness"),
    )
