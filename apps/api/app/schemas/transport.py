"""지도 transport 레이어 응답 schema — Map `/v1/service/transport/*` 투영 (ADR-076).

feature가 아니다. 항목의 ``feature_id``는 Map `make_feature_id` 값이라 PinVi POI·feature 상세가 쓰는 Map
PG feature UUID와 **다른 이름공간**이다(ADR-076 D7) — POI 추가·`/features/{id}`로 흘려보내지 않는다.

항목 모델은 Map 응답 해석에도 그대로 쓴다. **소비하는 필드만** 두고 나머지는 무시한다(``extra="ignore"``)
— Map의 additive 변경에 깨지지 않게 하고, 필드 이름·필수성 드리프트는 계약 게이트
(`tests/unit/test_kor_travel_map_transport_contract.py`)가 vendored OpenAPI와 대조해 잡는다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.feature import BBox

TransportLayer = Literal["fuel_station", "rest_area", "highway_incident", "airport"]
TRANSPORT_LAYERS: tuple[TransportLayer, ...] = (
    "fuel_station",
    "rest_area",
    "highway_incident",
    "airport",
)

#: 레이어를 읽을 수 없는 이유. 사용자 문구는 하나로 묶고 운영 진단에만 쓴다(ADR-076 D6). Map의 원문
#: 오류 메시지는 넘기지 않는다 — 이 enum만 노출한다.
TransportUnavailableReason = Literal[
    "NOT_LOADED",
    "STORE_UNAVAILABLE",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_AUTH",
    "UPSTREAM_REJECTED",
    "UPSTREAM_CONTRACT",
]


class _Upstream(BaseModel):
    """Map 응답 해석용 — 소비하지 않는 필드는 버린다."""

    model_config = ConfigDict(extra="ignore")


class TransportCoord(_Upstream):
    """WGS84 경위도(Map `StateCoordinate`). Map이 한국 주변 범위만 실어 보낸다."""

    lon: float = Field(ge=-180.0, le=180.0, allow_inf_nan=False)
    lat: float = Field(ge=-90.0, le=90.0, allow_inf_nan=False)


class TransportAddress(_Upstream):
    road: str | None = None
    jibun: str | None = None


class TransportFreshness(_Upstream):
    """데이터셋 세대 하나의 신선도(Map `TransportFreshness`)."""

    source_collected_at: AwareDatetime | None
    loaded_at: AwareDatetime
    age_seconds: int
    max_age_seconds: int
    stale: bool


class FuelPrice(_Upstream):
    """주유소 유종 하나의 현재가. ``price``가 null이면 지금 판매하지 않는다."""

    product_key: str
    product_code: str
    product_name: str | None = None
    price: float | None
    collected_at: AwareDatetime
    provider_updated_at: AwareDatetime | None = None


class RestAreaFuelPrices(_Upstream):
    """휴게소 주유소 최신 유가(원/L)."""

    gasoline_price: int | None = None
    diesel_price: int | None = None
    lpg_price: int | None = None
    oil_company: str | None = None
    observed_at: AwareDatetime


class _TransportItem(_Upstream):
    feature_id: str = Field(min_length=1, max_length=128)
    category: str
    marker_icon: str
    marker_color: str
    coord: TransportCoord | None
    distance_m: float | None = None


class FuelStationItem(_TransportItem):
    layer: Literal["fuel_station"] = "fuel_station"
    name: str
    address: TransportAddress
    brand_name: str | None = None
    phone: str | None = None
    is_self: bool | None = None
    is_24h: bool | None = None
    has_carwash: bool | None = None
    has_cvs: bool | None = None
    has_maintenance: bool | None = None
    lpg_available: bool | None = None
    prices: list[FuelPrice]


class RestAreaItem(_TransportItem):
    layer: Literal["rest_area"] = "rest_area"
    name: str
    address: TransportAddress
    route_name: str | None = None
    direction: str | None = None
    phone: str | None = None
    has_gas_station: bool | None = None
    has_lpg_station: bool | None = None
    has_ev_charger: bool | None = None
    fuel_prices: RestAreaFuelPrices | None = None


class HighwayIncidentItem(_TransportItem):
    layer: Literal["highway_incident"] = "highway_incident"
    title: str
    message: str | None = None
    incident_type: str | None = None
    process_status: str | None = None
    route_name: str | None = None
    direction: str | None = None
    point_name: str | None = None
    congestion_length: float | None = None
    occurred_at: AwareDatetime | None = None


class AirportItem(_TransportItem):
    layer: Literal["airport"] = "airport"
    name: str
    name_english: str
    iata_code: str
    icao_code: str | None = None
    municipality: str | None = None
    address: TransportAddress


TransportItem = Annotated[
    FuelStationItem | RestAreaItem | HighwayIncidentItem | AirportItem,
    Field(discriminator="layer"),
]


class TransportLayerResult(BaseModel):
    """레이어 하나의 viewport 결과. 실패는 HTTP 오류가 아니라 ``status``로 강등한다."""

    layer: TransportLayer
    status: Literal["ok", "unavailable", "disabled"]
    reason: TransportUnavailableReason | None = None
    freshness: TransportFreshness | None = None
    #: 휴게소만 — 휴게소 유가 데이터셋의 신선도(적재 전이면 null).
    fuel_price_freshness: TransportFreshness | None = None
    truncated: bool = False
    items: list[TransportItem] = Field(default_factory=list)


class TransportMarkersInBoundsResponse(BaseModel):
    """`GET /transport/markers-in-bounds`."""

    bbox: BBox
    zoom: int
    layers: list[TransportLayerResult]


class TransportLayerStatus(BaseModel):
    layer: TransportLayer
    available: bool
    reason: TransportUnavailableReason | None = None
    freshness: TransportFreshness | None = None


class TransportStatusResponse(BaseModel):
    """`GET /transport/status` — ``enabled=false``면 클라이언트는 레이어 컨트롤을 숨긴다."""

    enabled: bool
    layers: list[TransportLayerStatus] = Field(default_factory=list)


class TransportDetailResponse(BaseModel):
    """`GET /transport/{dataset}/{feature_id}`."""

    item: TransportItem
    freshness: TransportFreshness
    fuel_price_freshness: TransportFreshness | None = None


#: Map `PriceHistoryBlock.reason` enum. 모르는 값은 `upstream_contract`로 접는다(원문 비노출).
PriceHistoryUnavailableReason = Literal[
    "disabled",
    "not_configured",
    "upstream_not_found",
    "upstream_unavailable",
    "upstream_rejected",
    "upstream_contract",
]
PRICE_HISTORY_REASONS: tuple[str, ...] = (
    "disabled",
    "not_configured",
    "upstream_not_found",
    "upstream_unavailable",
    "upstream_rejected",
    "upstream_contract",
)


class FuelPriceHistoryPoint(_Upstream):
    product_key: str
    product_name: str | None = None
    price: float | None
    observed_at: AwareDatetime


class FuelPriceHistoryResponse(BaseModel):
    """`GET /transport/fuel-stations/{feature_id}/price-history`.

    ``status=unavailable``은 오류가 아니다 — Map이 추이를 지금 주지 못한다는 뜻이고 ``reason``이 이유다
    (`disabled`면 transport가 아직 추이를 내보내지 않는다).
    """

    feature_id: str
    status: Literal["available", "unavailable"]
    reason: PriceHistoryUnavailableReason | None = None
    truncated: bool = False
    items: list[FuelPriceHistoryPoint] = Field(default_factory=list)
    current_prices: list[FuelPrice] = Field(default_factory=list)
    freshness: TransportFreshness
