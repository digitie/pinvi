from __future__ import annotations

from datetime import date, time

import pytest
from opinet import (
    AreaCode as OpinetAreaCode,
)
from opinet import (
    AvgPrice as OpinetAvgPrice,
)
from opinet import (
    BrandCode as OpinetBrandCode,
)
from opinet import (
    ProductCode as OpinetProductCode,
)
from opinet import (
    Station as OpinetStation,
)

from app.core.config import Settings
from app.etl.fuel.opinet_source import (
    FuelRegionCodeLevel,
    FuelStationSort,
    FuelType,
    OpinetFailureKind,
    OpinetFuelSource,
    OpinetSourceError,
    build_opinet_client,
    fuel_type_from_provider_product_code,
    provider_product_code_for_fuel_type,
)


class _FakeOpinetClient:
    def __init__(
        self,
        *,
        averages: list[object] | None = None,
        stations: list[object] | None = None,
        areas: list[object] | None = None,
    ) -> None:
        self.averages = averages or []
        self.stations = stations or []
        self.areas = areas or []
        self.lowest_calls: list[tuple[object, int, str | None]] = []
        self.around_calls: list[dict[str, object]] = []
        self.area_calls: list[str | None] = []

    def get_national_average_price(self) -> list[object]:
        return self.averages

    def get_lowest_price_top20(
        self,
        prodcd: object,
        cnt: int = 10,
        area: str | None = None,
    ) -> list[object]:
        self.lowest_calls.append((prodcd, cnt, area))
        return self.stations

    def search_stations_around(
        self,
        *,
        wgs84: tuple[float, float] | None = None,
        katec: tuple[float, float] | None = None,
        radius_m: int = 5000,
        prodcd: object = "B027",
        sort: object = "1",
    ) -> list[object]:
        self.around_calls.append(
            {
                "wgs84": wgs84,
                "katec": katec,
                "radius_m": radius_m,
                "prodcd": prodcd,
                "sort": sort,
            }
        )
        return self.stations

    def get_area_codes(self, sido: str | None = None) -> list[object]:
        self.area_calls.append(sido)
        return self.areas


class OpinetRateLimitError(Exception):
    pass


class _FailingOpinetClient(_FakeOpinetClient):
    def get_national_average_price(self) -> list[object]:
        raise OpinetRateLimitError("quota exceeded")


def test_product_code_mapping_keeps_tripmate_enum_scope_and_provider_code() -> None:
    assert provider_product_code_for_fuel_type(FuelType.GASOLINE) == "B027"
    assert provider_product_code_for_fuel_type(FuelType.PREMIUM_GASOLINE) == "B034"
    assert provider_product_code_for_fuel_type(FuelType.DIESEL) == "D047"
    assert provider_product_code_for_fuel_type(FuelType.LPG) == "K015"
    assert fuel_type_from_provider_product_code(OpinetProductCode.GASOLINE) == FuelType.GASOLINE
    assert fuel_type_from_provider_product_code("C004") is None


def test_national_average_prices_are_normalized_from_python_opinet_api_rows() -> None:
    client = _FakeOpinetClient(
        averages=[
            OpinetAvgPrice(
                trade_date=date(2026, 5, 6),
                product_code=OpinetProductCode.GASOLINE,
                product_name="휘발유",
                price=1710.42,
                diff=-0.8,
                raw={"PRODCD": "B027", "PRODNM": "휘발유", "PRICE": "1710.42"},
            ),
            OpinetAvgPrice(
                trade_date=date(2026, 5, 6),
                product_code=OpinetProductCode.KEROSENE,
                product_name="실내등유",
                price=1390.0,
                diff=0.0,
                raw={"PRODCD": "C004", "PRODNM": "실내등유", "PRICE": "1390"},
            ),
        ]
    )
    source = OpinetFuelSource(client)

    rows = source.get_national_average_prices()

    assert rows[0].provider == "opinet"
    assert rows[0].provider_endpoint == "avgAllPrice.do"
    assert rows[0].provider_fuel_code == "B027"
    assert rows[0].provider_fuel_name == "휘발유"
    assert rows[0].fuel_type == FuelType.GASOLINE
    assert rows[0].price == 1710.42
    assert rows[0].diff == -0.8
    assert rows[0].price_timestamp.isoformat() == "2026-05-06T00:00:00+09:00"
    assert rows[0].provider_payload["product_code"] == "B027"
    assert rows[1].provider_fuel_code == "C004"
    assert rows[1].fuel_type is None


def test_lowest_price_stations_pass_region_and_limit_to_python_opinet_api() -> None:
    station = _station_row(distance_m=None, product_code=OpinetProductCode.DIESEL)
    client = _FakeOpinetClient(stations=[station])
    source = OpinetFuelSource(client)

    rows = source.get_lowest_price_stations(
        FuelType.DIESEL,
        limit=7,
        region_code="0113",
    )

    assert client.lowest_calls == [("D047", 7, "0113")]
    assert rows[0].provider_endpoint == "lowTop10.do"
    assert rows[0].provider_station_id == "A0010207"
    assert rows[0].provider_fuel_code == "D047"
    assert rows[0].provider_fuel_name is None
    assert rows[0].fuel_type == FuelType.DIESEL
    assert rows[0].brand_code == "SKE"
    assert rows[0].price == 1599.0
    assert rows[0].price_timestamp is None
    assert rows[0].lon == 127.0276
    assert rows[0].lat == 37.4979
    assert rows[0].provider_payload["brand"] == "SKE"


def test_search_stations_around_uses_wgs84_lon_lat_and_sort_code() -> None:
    client = _FakeOpinetClient(
        stations=[_station_row(distance_m=482.4, product_code=OpinetProductCode.GASOLINE)]
    )
    source = OpinetFuelSource(client)

    rows = source.search_stations_around(
        lon=127.0276,
        lat=37.4979,
        radius_m=3000,
        fuel_type=FuelType.GASOLINE,
        sort=FuelStationSort.DISTANCE,
    )

    assert client.around_calls == [
        {
            "wgs84": (127.0276, 37.4979),
            "katec": None,
            "radius_m": 3000,
            "prodcd": "B027",
            "sort": "2",
        }
    ]
    assert rows[0].provider_endpoint == "aroundAll.do"
    assert rows[0].distance_m == 482.4


def test_region_codes_keep_opinet_code_and_bjd_sido_mapping() -> None:
    client = _FakeOpinetClient(
        areas=[
            OpinetAreaCode(code="01", name="서울", raw={"AREA_CD": "01", "AREA_NM": "서울"}),
            OpinetAreaCode(
                code="0113", name="강남구", raw={"AREA_CD": "0113", "AREA_NM": "강남구"}
            ),
        ]
    )
    source = OpinetFuelSource(client)

    rows = source.get_region_codes()

    assert client.area_calls == [None]
    assert rows[0].provider_region_code == "01"
    assert rows[0].code_level == FuelRegionCodeLevel.SIDO
    assert rows[0].parent_provider_region_code is None
    assert rows[0].legal_dong_sido_prefix == "11"
    assert rows[1].provider_region_code == "0113"
    assert rows[1].code_level == FuelRegionCodeLevel.SIGUNGU
    assert rows[1].parent_provider_region_code == "01"
    assert rows[1].legal_dong_sido_prefix == "11"


def test_region_code_rejects_unexpected_provider_code_shape() -> None:
    client = _FakeOpinetClient(areas=[OpinetAreaCode(code="001", name="잘못된 코드")])
    source = OpinetFuelSource(client)

    with pytest.raises(OpinetSourceError) as exc_info:
        source.get_region_codes()

    assert exc_info.value.kind == OpinetFailureKind.INVALID_PARAMETER
    assert exc_info.value.dataset == "fuel_region_code"


def test_python_opinet_api_error_is_mapped_to_dataset_failure_kind() -> None:
    source = OpinetFuelSource(
        _FailingOpinetClient(),
    )

    with pytest.raises(OpinetSourceError) as exc_info:
        source.get_national_average_prices()

    assert exc_info.value.kind == OpinetFailureKind.RATE_LIMIT
    assert exc_info.value.dataset == "fuel_avg_price"


def test_build_opinet_client_imports_configured_dependency_without_network_call() -> None:
    client = build_opinet_client(
        Settings(
            opinet_api_key="dummy-key",
            opinet_timeout_seconds=1.5,
            opinet_max_retries=0,
            opinet_retry_backoff_seconds=0.0,
        )
    )

    assert client is not None


def test_station_trade_context_is_normalized_to_kst_timestamp() -> None:
    client = _FakeOpinetClient(
        stations=[
            _station_row(
                distance_m=None,
                product_code=OpinetProductCode.DIESEL,
                product_name="provider diesel",
                trade_date=date(2026, 5, 6),
                trade_time=time(14, 56, 18),
                raw={"PRODCD": "D047", "TRADE_DT": "20260506", "TRADE_TM": "145618"},
            )
        ]
    )
    source = OpinetFuelSource(client)

    rows = source.get_lowest_price_stations(FuelType.DIESEL, limit=1)

    assert rows[0].provider_fuel_name == "provider diesel"
    assert rows[0].price_timestamp is not None
    assert rows[0].price_timestamp.isoformat() == "2026-05-06T14:56:18+09:00"
    assert rows[0].provider_payload["TRADE_DT"] == "20260506"


def _station_row(
    *,
    distance_m: float | None,
    product_code: OpinetProductCode | None = None,
    product_name: str | None = None,
    trade_date: date | None = None,
    trade_time: time | None = None,
    raw: dict[str, object] | None = None,
) -> OpinetStation:
    return OpinetStation(
        uni_id="A0010207",
        name="테스트주유소",
        brand=OpinetBrandCode.SKE,
        price=1599.0,
        address_jibun="서울 강남구 역삼동 1",
        address_road="서울 강남구 테헤란로 1",
        katec_x=314871.8,
        katec_y=544012.0,
        lon=127.0276,
        lat=37.4979,
        distance_m=distance_m,
        product_code=product_code,
        product_name=product_name,
        trade_date=trade_date,
        trade_time=trade_time,
        raw=raw or {},
    )
