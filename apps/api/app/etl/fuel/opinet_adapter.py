from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, cast

from app.core.config import Settings, get_settings

OPINET_PROVIDER = "opinet"


class FuelType(StrEnum):
    GASOLINE = "gasoline"
    PREMIUM_GASOLINE = "premium_gasoline"
    DIESEL = "diesel"
    LPG = "lpg"


class FuelRegionCodeLevel(StrEnum):
    SIDO = "sido"
    SIGUNGU = "sigungu"


class FuelStationSort(StrEnum):
    PRICE = "price"
    DISTANCE = "distance"


class OpinetFailureKind(StrEnum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    INVALID_PARAMETER = "invalid_parameter"
    NO_DATA = "no_data"
    NETWORK = "network"
    UPSTREAM = "upstream"
    CONFIGURATION = "configuration"


class OpinetAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: OpinetFailureKind,
        dataset: str,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.dataset = dataset


@dataclass(frozen=True, slots=True)
class NormalizedFuelAverage:
    provider: str
    provider_endpoint: str
    provider_fuel_code: str
    provider_fuel_name: str
    fuel_type: FuelType | None
    trade_date: date
    price_timestamp: datetime
    price: float
    diff: float
    pyopinet_payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class NormalizedFuelStation:
    provider: str
    provider_endpoint: str
    provider_station_id: str
    provider_fuel_code: str
    provider_fuel_name: str | None
    fuel_type: FuelType | None
    name: str
    brand_code: str | None
    price: float | None
    price_timestamp: datetime | None
    address_jibun: str | None
    address_road: str | None
    katec_x: float
    katec_y: float
    lon: float
    lat: float
    distance_m: float | None
    pyopinet_payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class NormalizedFuelRegionCode:
    provider: str
    provider_endpoint: str
    provider_region_code: str
    provider_region_name: str
    code_level: FuelRegionCodeLevel
    parent_provider_region_code: str | None
    legal_dong_sido_prefix: str
    pyopinet_payload: dict[str, object]


class _AveragePriceLike(Protocol):
    def to_normalized(self, *, endpoint: str = "avgAllPrice.do") -> _NormalizedAverageLike: ...


class _StationLike(Protocol):
    def to_normalized(self, *, endpoint: str) -> _NormalizedStationLike: ...


class _AreaCodeLike(Protocol):
    def to_normalized(self, *, endpoint: str = "areaCode.do") -> _NormalizedRegionCodeLike: ...


class _NormalizedAverageLike(Protocol):
    provider_product_code: str
    provider_product_name: str
    fuel_type: object
    trade_date: date
    price: float
    diff: float
    raw: Mapping[str, object]

    def price_datetime(self) -> datetime: ...


class _NormalizedStationLike(Protocol):
    provider_station_id: str
    provider_station_name: str
    provider_product_code: str | None
    provider_product_name: str | None
    fuel_type: object
    brand_code: str | None
    price: float | None
    address_jibun: str | None
    address_road: str | None
    katec_x: float
    katec_y: float
    lon: float
    lat: float
    distance_m: float | None
    raw: Mapping[str, object]

    def trade_datetime(self) -> datetime | None: ...


class _NormalizedRegionCodeLike(Protocol):
    provider_region_code: str
    provider_region_name: str
    code_level: str
    parent_sido_code: str | None
    bjd_sido_prefix: str
    raw: Mapping[str, object]


class _OpinetClientLike(Protocol):
    def get_national_average_price(self) -> Sequence[_AveragePriceLike]: ...

    def get_lowest_price_top20(
        self,
        prodcd: object,
        cnt: int = 10,
        area: str | None = None,
    ) -> Sequence[_StationLike]: ...

    def search_stations_around(
        self,
        *,
        wgs84: tuple[float, float] | None = None,
        katec: tuple[float, float] | None = None,
        radius_m: int = 5000,
        prodcd: object = "B027",
        sort: object = "1",
    ) -> Sequence[_StationLike]: ...

    def get_area_codes(self, sido: str | None = None) -> Sequence[_AreaCodeLike]: ...


def build_opinet_client(settings: Settings | None = None) -> _OpinetClientLike:
    resolved_settings = settings or get_settings()
    try:
        from opinet import OpinetClient
    except ModuleNotFoundError as exc:
        raise OpinetAdapterError(
            "python-opinet-api(opinet) dependency is not installed.",
            kind=OpinetFailureKind.CONFIGURATION,
            dataset="fuel",
        ) from exc

    return cast(
        _OpinetClientLike,
        OpinetClient(
            api_key=resolved_settings.opinet_api_key,
            timeout=resolved_settings.opinet_timeout_seconds,
            strict_empty=False,
            max_retries=resolved_settings.opinet_max_retries,
            retry_backoff=resolved_settings.opinet_retry_backoff_seconds,
        ),
    )


def build_opinet_fuel_adapter(settings: Settings | None = None) -> OpinetFuelAdapter:
    return OpinetFuelAdapter(build_opinet_client(settings))


class OpinetFuelAdapter:
    def __init__(self, client: object) -> None:
        self._client = cast(_OpinetClientLike, client)

    def get_national_average_prices(self) -> list[NormalizedFuelAverage]:
        return self._call(
            "fuel_avg_price",
            lambda: [
                _normalize_average_price(row) for row in self._client.get_national_average_price()
            ],
        )

    def get_lowest_price_stations(
        self,
        fuel_type: FuelType,
        *,
        limit: int = 20,
        region_code: str | None = None,
    ) -> list[NormalizedFuelStation]:
        provider_fuel_code = provider_product_code_for_fuel_type(fuel_type)
        return self._call(
            "fuel_lowest_station",
            lambda: [
                _normalize_station(
                    row,
                    provider_endpoint="lowTop10.do",
                    provider_fuel_code=provider_fuel_code,
                )
                for row in self._client.get_lowest_price_top20(
                    provider_fuel_code,
                    cnt=limit,
                    area=region_code,
                )
            ],
        )

    def search_stations_around(
        self,
        *,
        lon: float,
        lat: float,
        radius_m: int,
        fuel_type: FuelType = FuelType.GASOLINE,
        sort: FuelStationSort = FuelStationSort.PRICE,
    ) -> list[NormalizedFuelStation]:
        provider_fuel_code = provider_product_code_for_fuel_type(fuel_type)
        provider_sort = _pyopinet_sort_order(sort)
        return self._call(
            "fuel_station_around",
            lambda: [
                _normalize_station(
                    row,
                    provider_endpoint="aroundAll.do",
                    provider_fuel_code=provider_fuel_code,
                )
                for row in self._client.search_stations_around(
                    wgs84=(lon, lat),
                    radius_m=radius_m,
                    prodcd=provider_fuel_code,
                    sort=provider_sort,
                )
            ],
        )

    def get_region_codes(self, sido: str | None = None) -> list[NormalizedFuelRegionCode]:
        return self._call(
            "fuel_region_code",
            lambda: [
                self._normalize_region_code(row) for row in self._client.get_area_codes(sido=sido)
            ],
        )

    def _normalize_region_code(self, row: _AreaCodeLike) -> NormalizedFuelRegionCode:
        normalized = row.to_normalized(endpoint="areaCode.do")
        code_level = FuelRegionCodeLevel(normalized.code_level)
        return NormalizedFuelRegionCode(
            provider=OPINET_PROVIDER,
            provider_endpoint="areaCode.do",
            provider_region_code=normalized.provider_region_code,
            provider_region_name=normalized.provider_region_name,
            code_level=code_level,
            parent_provider_region_code=normalized.parent_sido_code,
            legal_dong_sido_prefix=normalized.bjd_sido_prefix,
            pyopinet_payload=_payload_from_raw(
                normalized.raw,
                code=normalized.provider_region_code,
                name=normalized.provider_region_name,
                is_sido=code_level == FuelRegionCodeLevel.SIDO,
                is_sigungu=code_level == FuelRegionCodeLevel.SIGUNGU,
            ),
        )

    def _call[T](self, dataset: str, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except OpinetAdapterError:
            raise
        except Exception as exc:
            raise _map_opinet_exception(dataset, exc) from exc


def provider_product_code_for_fuel_type(fuel_type: FuelType) -> str:
    try:
        from opinet import fuel_type_to_product_code
    except ModuleNotFoundError as exc:
        raise OpinetAdapterError(
            "python-opinet-api(opinet) dependency is not installed.",
            kind=OpinetFailureKind.CONFIGURATION,
            dataset="fuel",
        ) from exc
    return str(fuel_type_to_product_code(fuel_type.value).value)


def fuel_type_from_provider_product_code(provider_product_code: object) -> FuelType | None:
    try:
        from opinet import product_code_to_fuel_type
    except ModuleNotFoundError as exc:
        raise OpinetAdapterError(
            "python-opinet-api(opinet) dependency is not installed.",
            kind=OpinetFailureKind.CONFIGURATION,
            dataset="fuel",
        ) from exc
    try:
        pyopinet_fuel_type = product_code_to_fuel_type(_value(provider_product_code))
    except Exception as exc:
        if exc.__class__.__name__ == "OpinetInvalidParameterError":
            return None
        raise
    try:
        return FuelType(str(pyopinet_fuel_type.value))
    except ValueError:
        return None


def _normalize_average_price(row: _AveragePriceLike) -> NormalizedFuelAverage:
    normalized = row.to_normalized(endpoint="avgAllPrice.do")
    provider_fuel_code = normalized.provider_product_code
    provider_fuel_name = normalized.provider_product_name
    return NormalizedFuelAverage(
        provider=OPINET_PROVIDER,
        provider_endpoint="avgAllPrice.do",
        provider_fuel_code=provider_fuel_code,
        provider_fuel_name=provider_fuel_name,
        fuel_type=_tripmate_fuel_type_from_pyopinet(normalized.fuel_type),
        trade_date=normalized.trade_date,
        price_timestamp=normalized.price_datetime(),
        price=normalized.price,
        diff=normalized.diff,
        pyopinet_payload=_payload_from_raw(
            normalized.raw,
            trade_date=normalized.trade_date.isoformat(),
            product_code=provider_fuel_code,
            product_name=provider_fuel_name,
            price=normalized.price,
            diff=normalized.diff,
        ),
    )


def _normalize_station(
    row: _StationLike,
    *,
    provider_endpoint: str,
    provider_fuel_code: str,
) -> NormalizedFuelStation:
    normalized = row.to_normalized(endpoint=provider_endpoint)
    provider_fuel_code = normalized.provider_product_code or provider_fuel_code
    fuel_type = _tripmate_fuel_type_from_pyopinet(normalized.fuel_type)
    if fuel_type is None:
        fuel_type = fuel_type_from_provider_product_code(provider_fuel_code)
    trade_datetime = normalized.trade_datetime()
    return NormalizedFuelStation(
        provider=OPINET_PROVIDER,
        provider_endpoint=provider_endpoint,
        provider_station_id=normalized.provider_station_id,
        provider_fuel_code=provider_fuel_code,
        provider_fuel_name=normalized.provider_product_name,
        fuel_type=fuel_type,
        name=normalized.provider_station_name,
        brand_code=normalized.brand_code,
        price=normalized.price,
        price_timestamp=trade_datetime,
        address_jibun=normalized.address_jibun,
        address_road=normalized.address_road,
        katec_x=normalized.katec_x,
        katec_y=normalized.katec_y,
        lon=normalized.lon,
        lat=normalized.lat,
        distance_m=normalized.distance_m,
        pyopinet_payload=_payload_from_raw(
            normalized.raw,
            uni_id=normalized.provider_station_id,
            name=normalized.provider_station_name,
            brand=normalized.brand_code,
            product_code=provider_fuel_code,
            product_name=normalized.provider_product_name,
            price=normalized.price,
            trade_datetime=trade_datetime.isoformat() if trade_datetime is not None else None,
            address_jibun=normalized.address_jibun,
            address_road=normalized.address_road,
            katec_x=normalized.katec_x,
            katec_y=normalized.katec_y,
            lon=normalized.lon,
            lat=normalized.lat,
            distance_m=normalized.distance_m,
        ),
    )


def _value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    return str(raw_value)


def _tripmate_fuel_type_from_pyopinet(pyopinet_fuel_type: object) -> FuelType | None:
    try:
        return FuelType(_value(pyopinet_fuel_type))
    except ValueError:
        return None


def _pyopinet_sort_order(sort: FuelStationSort) -> object:
    try:
        from opinet import SortOrder
    except ModuleNotFoundError as exc:
        raise OpinetAdapterError(
            "python-opinet-api(opinet) dependency is not installed.",
            kind=OpinetFailureKind.CONFIGURATION,
            dataset="fuel",
        ) from exc
    if sort == FuelStationSort.PRICE:
        return SortOrder.PRICE
    return SortOrder.DISTANCE


def _payload_from_raw(raw: Mapping[str, object], **fallback: object) -> dict[str, object]:
    payload = dict(raw)
    for key, value in fallback.items():
        payload.setdefault(key, value)
    return payload


def _map_opinet_exception(dataset: str, exc: Exception) -> OpinetAdapterError:
    class_name = exc.__class__.__name__
    if class_name == "OpinetAuthError":
        kind = OpinetFailureKind.AUTH
    elif class_name == "OpinetRateLimitError":
        kind = OpinetFailureKind.RATE_LIMIT
    elif class_name == "OpinetInvalidParameterError":
        kind = OpinetFailureKind.INVALID_PARAMETER
    elif class_name == "OpinetNoDataError":
        kind = OpinetFailureKind.NO_DATA
    elif class_name == "OpinetNetworkError":
        kind = OpinetFailureKind.NETWORK
    else:
        kind = OpinetFailureKind.UPSTREAM
    return OpinetAdapterError(str(exc), kind=kind, dataset=dataset)


build_pyopinet_client = build_opinet_client
build_pyopinet_fuel_adapter = build_opinet_fuel_adapter
PyOpinetFuelAdapter = OpinetFuelAdapter
